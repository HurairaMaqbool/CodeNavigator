# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/confidence.py
-----------------------
Answer Validation, Hallucination Guard, Confidence Scoring & Gating.

Responsibility boundary
-----------------------
Takes the raw LLM output and retrieval signals, computes a deterministic confidence
score, gates low-confidence answers, and formats the final API response including
the `sources` array.
It does NOT:
  - iterate the RAG loop (Module 9a)
  - query external tools (Module 9a)

Confidence Score Formula Tradeoffs
----------------------------------
  0.50 * Retrieval (hybrid search rerank score)
  0.35 * Grounding (valid/invalid citations)
  0.15 * Citation density (up to 3 citations)
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.observability.logging_config import logger
from app.agent.response_firewall import sanitize_user_answer, has_forbidden_leak
from app.agent.citation_repair import repair_answer_citations
from app.agent.symbol_lookup import resolve_symbol_location

# ---------------------------------------------------------------------------
# Citation Extraction
# ---------------------------------------------------------------------------

# Matches inline backtick file citations.
# e.g., `src/auth/login.py:12` or `src/auth/login.py:12-14` or `src/auth/login.py`
FILE_PATH_PATTERN = re.compile(r'`([\w./\-]+\.(?:py|js|jsx|ts|tsx))(?:[:](\d+)(?:-(\d+))?)?`')

# Groq/Llama sometimes leaks tool calls into visible answer text.
FUNCTION_TAG_PATTERN = re.compile(
    r"<function=[a-zA-Z0-9_-]+>\s*\{.*?\}\s*(?:</function>)?",
    re.DOTALL,
)

# Matches inline backtick function calls.
# e.g., `authenticate_user()` or `self.auth.validate()` -> `validate`
FUNCTION_CALL_PATTERN = re.compile(r'`(?:[\w.]+\.)?(\w+)\(\)`')


def extract_file_mentions_with_lines(text: str) -> list[tuple[str, int | None, int | None]]:
    """Return all backtick-wrapped file paths mentioned and their line ranges."""
    matches = FILE_PATH_PATTERN.findall(text)
    mentions = []
    for match in matches:
        path = match[0]
        start = int(match[1]) if match[1] else None
        end = int(match[2]) if match[2] else start
        mentions.append((path, start, end))
    return mentions

def extract_file_path_mentions(text: str) -> list[str]:
    """Return all backtick-wrapped file paths mentioned without line numbers."""
    return [m[0] for m in extract_file_mentions_with_lines(text)]


def extract_function_name_mentions(text: str) -> list[str]:
    """Return all backtick-wrapped function names (last segment only)."""
    return FUNCTION_CALL_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# Repo Metadata Loading
# ---------------------------------------------------------------------------

def _load_repo_metadata(repo_id: str) -> list[dict[str, Any]]:
    """
    Load the metadata from the BM25 index (Module 6a) which contains all chunks.
    This is the cheapest way to get the exact file_path, function_name, and lines.
    """
    from app.retrieval.bm25_store import _index_path_for
    pkl_path = _index_path_for(repo_id)
    if not pkl_path.exists():
        return []
    
    try:
        with pkl_path.open("rb") as f:
            bm25, records = pickle.load(f)
        return [r["metadata"] for r in records]
    except Exception as e:
        logger.error("failed_to_load_bm25_metadata", error=str(e))
        return []


# ---------------------------------------------------------------------------
# Confidence Scoring
# ---------------------------------------------------------------------------

def compute_confidence_score(
    invalid_reference_ratio: float | None,
    top_retrieval_score: float | None,
    citation_count: int
) -> float:
    """
    Compute a deterministic confidence score (0.0 to 10.0).
    """
    # Retrieval component (50% weight) — now the dominant signal.
    # top_retrieval_score is the ABSOLUTE sigmoid relevance from the reranker
    # (see reranker.py), so a poor best-match correctly drags confidence down.
    # An answer grounded in irrelevant chunks must NOT score highly just because
    # it avoided hallucinating, which is why retrieval outweighs grounding here.
    retrieval_component = 10 * (top_retrieval_score or 0.0)

    # Grounding component (35% weight) — penalizes fabricated file/line refs.
    grounding_component = 10 * (1 - (invalid_reference_ratio or 0.0))

    # Citation component (15% weight) — caps at 3 so citation spam can't inflate.
    citation_component = min(citation_count, 3) / 3 * 10

    return round(
        0.50 * retrieval_component +
        0.35 * grounding_component +
        0.15 * citation_component,
        1
    )


# ---------------------------------------------------------------------------
# Validation and Gating
# ---------------------------------------------------------------------------

def _format_lines(meta: dict[str, Any]) -> str | None:
    start = meta.get("start_line")
    end = meta.get("end_line")
    if start is None:
        return None
    if end is not None and end != start:
        return f"{start}-{end}"
    return str(start)


def _build_sources_from_hits(
    retrieval_hits: list[dict[str, Any]],
    *,
    max_sources: int = 5,
) -> list[dict[str, Any]]:
    """Build sources from retrieval metadata (always includes line numbers)."""
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in sorted(retrieval_hits, key=lambda h: h.get("rerank_score", 0), reverse=True):
        fp = hit.get("file_path") or ""
        if not fp:
            continue
        fn = hit.get("function_name")
        lines = _format_lines(hit)
        sig = f"{fp}::{fn}::{lines}"
        if sig in seen:
            continue
        seen.add(sig)
        sources.append({
            "file_path": fp,
            "function_name": fn,
            "lines": lines,
            "snippet": (hit.get("chunk") or hit.get("snippet") or "")[:1200],
        })
        if len(sources) >= max_sources:
            break
    return sources


def _symbol_sources_from_text(
    repo_id: str,
    text: str,
    question: str | None,
    *,
    max_sources: int = 5,
) -> list[dict[str, Any]]:
    """Build sources from symbols mentioned in the question (and cited in the answer)."""
    from app.agent.citation_repair import _symbols_in_sentence

    symbols = _symbols_in_sentence(question or "")
    for sym in _symbols_in_sentence(text):
        if sym not in symbols and (
            sym.lower() in (question or "").lower() or f"`{sym}" in text
        ):
            symbols.append(sym)
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sym in symbols:
        loc = resolve_symbol_location(repo_id, sym, kind="class" if sym[0].isupper() else "function")
        if not loc:
            continue
        fp = loc["file_path"]
        lines = _format_lines(loc)
        sig = f"{fp}::{sym}::{lines}"
        if sig in seen:
            continue
        seen.add(sig)
        sources.append({
            "file_path": fp,
            "function_name": loc.get("function_name") or sym,
            "lines": lines,
        })
        if len(sources) >= max_sources:
            break
    return sources


def validate_and_return(
    answer_content: list[dict],
    repo_id: str,
    trace: list[dict],
    top_retrieval_score: float | None,
    retrieval_hits: list[dict[str, Any]] | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """
    Validate the raw LLM answer against known repo paths/functions, compute
    confidence, gate if too low, and assemble the final API response.
    """
    log = logger.bind(repo_id=repo_id)
    
    # Extract plain text from LLM content blocks and sanitize for UI
    text = "".join([b.get("text", "") for b in answer_content if b.get("type") == "text"])
    text = sanitize_user_answer(FUNCTION_TAG_PATTERN.sub("", text))
    text = repair_answer_citations(text, retrieval_hits, repo_id=repo_id, question=question)
    if has_forbidden_leak(text):
        text = sanitize_user_answer(text)
    
    # Extract mentions
    mentions = extract_file_mentions_with_lines(text)
    mentioned_paths = [m[0] for m in mentions]
    mentioned_functions = extract_function_name_mentions(text)
    
    # Load repo metadata
    repo_meta = _load_repo_metadata(repo_id)
    
    # Build fast lookup sets. Use .get() because metadata dicts may only have display_path (e.g. in tests)
    known_paths = (
        {m.get("display_path", "") for m in repo_meta}
        | {m.get("file_path", "") for m in repo_meta}
        | {m.get("normalized_path", "") for m in repo_meta}
    ) - {""}  # Remove empty strings from None .get() results
    known_functions = {m["function_name"] for m in repo_meta if m.get("function_name")}
    
    # Check validity
    invalid = []
    valid_paths = set()
    valid_functions = set()
    
    for path, start, end in mentions:
        if path in known_paths:
            if start is not None:
                clean_path = path.replace("\\", "/").lstrip("/")
                clone_marker = "/clone/"
                clone_idx = clean_path.find(clone_marker)
                if clone_idx != -1:
                    clean_path = clean_path[clone_idx + len(clone_marker):]
                else:
                    parts = clean_path.split("/")
                    if len(parts) > 2 and parts[0] == "repos" and parts[2] == "clone":
                        clean_path = "/".join(parts[3:])
                        
                abs_path = Path(settings.REPOS_PATH) / repo_id / "clone" / clean_path
                
                if abs_path.is_file():
                    try:
                        with open(abs_path, 'rb') as f:
                            lines_count = sum(1 for _ in f)
                        
                        if start > lines_count or (end is not None and end > lines_count):
                            invalid.append(f"{path}:{start}-{end}")
                        else:
                            valid_paths.add(path)
                    except Exception:
                        valid_paths.add(path)
                else:
                    valid_paths.add(path)
            else:
                valid_paths.add(path)
        else:
            invalid.append(path)
            
    for func in mentioned_functions:
        # Some methods are "ClassName.method_name" in metadata, but the regex extracts "method_name"
        # We need to check if the extracted func is exactly the function_name or the suffix of a class method.
        # It's safest to check if func matches any function_name or is the right side of a dot in known_functions.
        found = False
        for kf in known_functions:
            if kf == func or kf.endswith(f".{func}"):
                found = True
                break
        if found:
            valid_functions.add(func)
        else:
            invalid.append(func)
            
    total_mentions = len(mentioned_paths) + len(mentioned_functions)
    
    # Ratio calculation
    if total_mentions == 0:
        invalid_reference_ratio = None
    else:
        invalid_reference_ratio = len(invalid) / total_mentions
        
    # Confidence
    confidence_score = compute_confidence_score(
        invalid_reference_ratio=invalid_reference_ratio,
        top_retrieval_score=top_retrieval_score,
        citation_count=total_mentions
    )
    
    # Gate check
    gate_threshold = settings.MIN_CONFIDENCE_SCORE
    if confidence_score < gate_threshold:
        log.warning("answer_gated", score=confidence_score, invalid_ratio=invalid_reference_ratio)
        partial_sources = _build_sources_from_hits(retrieval_hits or [], max_sources=3)
        if partial_sources:
            paths = ", ".join(f"`{s['file_path']}`" for s in partial_sources[:3])
            answer = (
                "I found related code but could not verify a complete answer. "
                f"Closest matches: {paths}. "
                "Try a more specific class or function name."
            )
        else:
            answer = (
                "I could not find enough reliable context in the indexed files. "
                "Try naming a specific class, function, or file path."
            )
        return {
            "answer": sanitize_user_answer(answer),
            "sources": partial_sources,
            "confidence": "low",
            "gated": True,
            "confidence_score": confidence_score,
            "invalid_reference_ratio": invalid_reference_ratio,
            "trace": trace,
            "retrieval_hits": retrieval_hits or [],
        }
        
    # Build Sources Array
    sources = []
    seen_sources = set()
    
    for path in valid_paths:
        # Find all metadata records matching this path
        matches = [
            m for m in repo_meta
            if (
                m.get("display_path") == path
                or m.get("file_path") == path
                or m.get("normalized_path") == path
            )
        ]
        # For each valid function mentioned, if it belongs to this file, we add it.
        # If no valid function is explicitly mentioned for this file, we just add the file itself.
        funcs_in_file = []
        for m in matches:
            fn = m.get("function_name")
            if fn:
                # Does the valid function list match this function?
                if fn in valid_functions or fn.split(".")[-1] in valid_functions:
                    funcs_in_file.append(m)
                    
        if funcs_in_file:
            for f_meta in funcs_in_file:
                fn = f_meta["function_name"]
                lines = f"{f_meta['start_line']}-{f_meta['end_line']}"
                sig = f"{path}::{fn}::{lines}"
                if sig not in seen_sources:
                    seen_sources.add(sig)
                    sources.append({
                        "file_path": f_meta["display_path"],
                        "function_name": fn,
                        "lines": lines
                    })
        else:
            if matches:
                best = matches[0]
                lines = _format_lines(best)
                sig = f"{path}::{best.get('function_name')}::{lines}"
                if sig not in seen_sources:
                    seen_sources.add(sig)
                    sources.append({
                        "file_path": best.get("display_path") or path,
                        "function_name": best.get("function_name"),
                        "lines": lines,
                    })

    # Merge top retrieval hits so sources always carry line numbers
    for hit_src in _build_sources_from_hits(retrieval_hits or [], max_sources=5):
        sig = f"{hit_src['file_path']}::{hit_src.get('function_name')}::{hit_src.get('lines')}"
        if sig not in seen_sources:
            seen_sources.add(sig)
            sources.append(hit_src)

    # Prefer symbol-resolved sources (correct class/def lines) over raw retrieval chunks
    sym_sources = _symbol_sources_from_text(repo_id, text, question, max_sources=2)
    if sym_sources:
        sources = sym_sources[:2]
    else:
        # Deduplicate by file_path, keep highest-scored order
        deduped: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for s in sources:
            fp = s["file_path"]
            if fp in seen_files:
                continue
            seen_files.add(fp)
            deduped.append(s)
        sources = deduped[:3]
                    
    # Above-gate bucketing
    if confidence_score >= 7.0:
        confidence_label = "high"
    elif confidence_score >= 4.0:
        confidence_label = "medium"
    else:
        confidence_label = "low"
        
    response: dict[str, Any] = {
        "answer": sanitize_user_answer(text),
        "sources": sources,
        "confidence": confidence_label,
        "confidence_score": confidence_score,
        "invalid_reference_ratio": invalid_reference_ratio,
        "gated": False,
        "trace": trace,
        "retrieval_hits": retrieval_hits or [],
    }
    
    if invalid:
        response["warning"] = f"The following references could not be verified in the codebase: {', '.join(invalid)}"
        
    return response
