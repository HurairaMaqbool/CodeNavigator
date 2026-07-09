# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/confidence.py
-----------------------
Module #26 — Hallucination Guard v2 (VERIFY state).

Deterministic citation checks (file existence, line bounds, graph consistency)
with zero LLM cost. Legacy ``validate_and_return`` / ``compute_confidence_score``
remain for Module 9b compatibility.
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.ingestion.metadata_store import metadata_store
from app.observability.logging_config import logger
from app.agent.response_firewall import sanitize_user_answer, has_forbidden_leak
from app.agent.citation_repair import repair_answer_citations
from app.agent.symbol_lookup import resolve_symbol_location

# ---------------------------------------------------------------------------
# Module #26 — VERIFY scoring constants
# ---------------------------------------------------------------------------

BASE_CONFIDENCE_SCORE: float = 10.0
PENALTY_FILE_EXISTENCE: float = 4.0
PENALTY_LINE_BOUNDS: float = 3.0
PENALTY_GRAPH_CONSISTENCY: float = 3.0

GATED_FALLBACK_MESSAGE: str = (
    "I could not verify the cited references in the indexed codebase. "
    "Please try again with a more specific class, function, or file path."
)

# finalize_prompt.py format: `file_path:start_line-end_line` (e.g. `src/auth/login.py:42-58`)
CITATION_LINE_RANGE_PATTERN = re.compile(
    r"`((?:[\w./\\\-@]+/)?[\w.\-]+\.[\w]{1,12}):(\d+)(?:-(\d+))?`",
    re.IGNORECASE,
)

_BACKTICK_SPAN_PATTERN = re.compile(r"`([^`]+)`")
_FILE_LIKE_PATTERN = re.compile(r"[\w./\-]+\.[\w]{1,12}", re.IGNORECASE)
FUNCTION_CALL_PATTERN = re.compile(r"`(?:[\w.]+\.)?(\w+)\(\)`")

# ---------------------------------------------------------------------------
# Module #26 — VERIFY public API
# ---------------------------------------------------------------------------

def parse_citations(answer: str) -> list[dict[str, Any]]:
    """
    Parse markdown citations matching finalize_prompt's ``file_path:start_line-end_line``.

    ``function_name`` is the nearest preceding ``func()`` backtick reference before
    each citation span in the answer text (same convention as legacy grounding).
    Unparseable file-like backtick spans are returned with ``unparseable=True``.
    """
    if not answer:
        return []

    citations: list[dict[str, Any]] = []
    covered: set[tuple[int, int]] = set()

    for match in CITATION_LINE_RANGE_PATTERN.finditer(answer):
        start_line = int(match.group(2))
        end_raw = match.group(3)
        end_line = int(end_raw) if end_raw else start_line
        span = (match.start(), match.end())
        covered.add(span)
        citations.append({
            "file_path": match.group(1),
            "start_line": start_line,
            "end_line": end_line,
            "function_name": _function_name_before(answer, match.start()),
            "unparseable": False,
        })

    for match in _BACKTICK_SPAN_PATTERN.finditer(answer):
        span = (match.start(), match.end())
        if span in covered:
            continue
        inner = match.group(1).strip()
        if not inner:
            continue
        if CITATION_LINE_RANGE_PATTERN.fullmatch(f"`{inner}`"):
            continue
        if _FILE_LIKE_PATTERN.search(inner) or (":" in inner and _FILE_LIKE_PATTERN.search(inner.split(":")[0])):
            citations.append({
                "file_path": inner.split(":")[0] if ":" in inner else inner,
                "start_line": None,
                "end_line": None,
                "function_name": _function_name_before(answer, match.start()),
                "unparseable": True,
            })
            covered.add(span)

    return citations


def _function_name_before(answer: str, position: int) -> str | None:
    prefix = answer[:position]
    matches = list(FUNCTION_CALL_PATTERN.finditer(prefix))
    if not matches:
        return None
    return matches[-1].group(1)


def check_file_existence(citation: dict[str, Any]) -> bool:
    """
    Confirm ``file_path`` exists in the indexed file set for the current commit.

    Uses ``metadata_store`` sync status plus BM25/chunk metadata paths built at index time.
    """
    if citation.get("unparseable"):
        return False
    repo_id = str(citation.get("repo_id", ""))
    if not repo_id:
        return False

    meta = metadata_store.get(repo_id)
    if meta is None or meta.sync_status != "synced":
        return False

    path = _normalize_repo_path(str(citation.get("file_path", "")))
    if not path:
        return False

    known = _indexed_paths_for_repo(repo_id)
    if path in known:
        return True

    # Physical clone check as secondary confirmation for indexed repos.
    clone_path = _clone_file_path(repo_id, path)
    return clone_path is not None and clone_path.is_file()


def check_line_bounds(citation: dict[str, Any]) -> bool:
    """Confirm cited line numbers fall within the real file length / chunk metadata."""
    if citation.get("unparseable"):
        return False

    start = citation.get("start_line")
    end = citation.get("end_line") or start
    if start is None or end is None:
        return False

    repo_id = str(citation.get("repo_id", ""))
    path = _normalize_repo_path(str(citation.get("file_path", "")))
    if not repo_id or not path:
        return False

    if end < start:
        return False

    line_count = _clone_file_line_count(repo_id, path)
    if line_count is not None:
        return 1 <= start <= line_count and 1 <= end <= line_count

    return _lines_covered_by_chunk_metadata(repo_id, path, int(start), int(end))


def check_graph_consistency(citation: dict[str, Any]) -> bool:
    """Confirm cited ``function_name`` is a node in the persisted call graph."""
    fn = citation.get("function_name")
    if not fn:
        return True

    if citation.get("unparseable"):
        return False

    repo_id = str(citation.get("repo_id", ""))
    if not repo_id:
        return False

    from app.graph.builder import get_graph

    graph = get_graph(repo_id)
    if graph is None or graph.number_of_nodes() == 0:
        return False

    cite_path = _normalize_repo_path(str(citation.get("file_path", "")))
    for node_id, data in graph.nodes(data=True):
        node_name = str(data.get("name", node_id.rpartition(":")[2]))
        node_path = _normalize_repo_path(str(data.get("path", node_id.rpartition(":")[0])))
        name_match = (
            node_name == fn
            or node_name.endswith(f".{fn}")
            or node_name.split(".")[-1] == fn
        )
        if not name_match:
            continue
        if cite_path and node_path and cite_path != node_path:
            continue
        return True
    return False


def evaluate(answer: str, repo_id: str) -> dict[str, Any]:
    """
    VERIFY-state guard — deterministic scoring with zero LLM calls.

    Aggregation: start at ``BASE_CONFIDENCE_SCORE`` (10.0), subtract fixed penalties
    for every failed check on every citation (including unparseable spans as file
    existence failures). Score is floored at 0.0. Gate when below ``settings.MIN_CONFIDENCE_SCORE``.
    """
    try:
        citations = parse_citations(answer or "")
        score = BASE_CONFIDENCE_SCORE

        for citation in citations:
            citation["repo_id"] = repo_id
            if citation.get("unparseable"):
                score -= PENALTY_FILE_EXISTENCE
                continue

            if not check_file_existence(citation):
                score -= PENALTY_FILE_EXISTENCE
            if not check_line_bounds(citation):
                score -= PENALTY_LINE_BOUNDS
            if not check_graph_consistency(citation):
                score -= PENALTY_GRAPH_CONSISTENCY

        score = max(0.0, round(score, 1))
        gated = score < settings.MIN_CONFIDENCE_SCORE

        if gated:
            logger.warning("verify_gated", repo_id=repo_id, score=score)
            return {
                "answer": GATED_FALLBACK_MESSAGE,
                "confidence_score": score,
                "gated": True,
            }

        return {
            "answer": answer,
            "confidence_score": score,
            "gated": False,
        }
    except Exception as exc:
        logger.warning("verify_evaluate_failed", repo_id=repo_id, error=str(exc))
        return {
            "answer": GATED_FALLBACK_MESSAGE,
            "confidence_score": 0.0,
            "gated": True,
        }


# ---------------------------------------------------------------------------
# Module #26 — lookup helpers (metadata_store + chunk index + clone + graph)
# ---------------------------------------------------------------------------

def _normalize_repo_path(path: str) -> str:
    clean = path.replace("\\", "/").strip().lstrip("/")
    clone_marker = "/clone/"
    idx = clean.find(clone_marker)
    if idx != -1:
        clean = clean[idx + len(clone_marker):]
    parts = clean.split("/")
    if len(parts) > 2 and parts[0] == "repos" and parts[2] == "clone":
        clean = "/".join(parts[3:])
    return clean


def _indexed_paths_for_repo(repo_id: str) -> set[str]:
    paths: set[str] = set()
    for meta in _load_repo_metadata(repo_id):
        for key in ("display_path", "file_path", "normalized_path"):
            val = meta.get(key)
            if val:
                paths.add(_normalize_repo_path(str(val)))
    return paths


def _clone_file_path(repo_id: str, file_path: str) -> Path | None:
    if not file_path:
        return None
    return Path(settings.REPOS_PATH) / repo_id / "clone" / file_path


def _clone_file_line_count(repo_id: str, file_path: str) -> int | None:
    abs_path = _clone_file_path(repo_id, file_path)
    if abs_path is None or not abs_path.is_file():
        return None
    try:
        with abs_path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def _lines_covered_by_chunk_metadata(repo_id: str, file_path: str, start: int, end: int) -> bool:
    norm = _normalize_repo_path(file_path)
    for meta in _load_repo_metadata(repo_id):
        meta_path = _normalize_repo_path(
            str(meta.get("display_path") or meta.get("file_path") or meta.get("normalized_path") or "")
        )
        if meta_path != norm:
            continue
        chunk_start = int(meta.get("start_line") or 0)
        chunk_end = int(meta.get("end_line") or chunk_start)
        if chunk_start <= start and end <= chunk_end:
            return True
    return False


# ---------------------------------------------------------------------------
# Legacy citation extraction (Module 9b)
# ---------------------------------------------------------------------------

# Matches inline backtick file citations.
# e.g., `src/auth/login.py:12` or `src/auth/login.py:12-14` or `src/auth/login.py`
FILE_PATH_PATTERN = re.compile(r'`([\w./\-]+\.(?:py|js|jsx|ts|tsx))(?:[:](\d+)(?:-(\d+))?)?`')

# Groq/Llama sometimes leaks tool calls into visible answer text.
FUNCTION_TAG_PATTERN = re.compile(
    r"<function=[a-zA-Z0-9_-]+>\s*\{.*?\}\s*(?:</function>)?",
    re.DOTALL,
)

# Matches inline backtick function calls (legacy extractors).
# e.g., `authenticate_user()` or `self.auth.validate()` -> `validate`


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
