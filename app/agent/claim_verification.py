# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/claim_verification.py
-------------------------------
Layer 3 — Atomic claim verification against cited chunk text.

Uses local embedding similarity (cheap, batched) with an optional single
batched LLM yes/no pass for borderline claims.
"""
from __future__ import annotations

import json
import math
import re
import time
from typing import Any

from app.agent.confidence import (
    check_file_existence,
    check_line_bounds,
    path_key,
)
from app.agent.grounding import is_abstention_claim, is_factual_claim, strip_json_fences
from app.config import settings
from app.observability.logging_config import logger


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _hit_path(hit: dict[str, Any]) -> str:
    meta = hit.get("chunk_metadata") or hit
    return path_key(str(meta.get("display_path") or meta.get("file_path") or ""))


def _hit_text(hit: dict[str, Any]) -> str:
    meta = hit.get("chunk_metadata") or hit
    return str(hit.get("chunk") or hit.get("snippet") or meta.get("chunk") or meta.get("snippet") or "")


def _retrieval_text_for_citation(
    norm_path: str,
    start_line: int,
    end_line: int,
    retrieval_hits: list[dict[str, Any]] | None,
    *,
    path_only: bool = False,
) -> str:
    """Pick best chunk text from live retrieval hits (overlap first, then path match)."""
    best_overlap = 0
    best_text = ""
    path_fallback = ""
    for hit in retrieval_hits or []:
        hp = _hit_path(hit)
        if hp != norm_path:
            continue
        text = _hit_text(hit).strip()
        if not text:
            continue
        if not path_fallback:
            path_fallback = text
        if path_only:
            continue
        meta = hit.get("chunk_metadata") or hit
        cs = int(meta.get("start_line") or 0)
        ce = int(meta.get("end_line") or cs)
        if cs < 1:
            continue
        overlap = max(0, min(end_line, ce) - max(start_line, cs) + 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = text
    chosen = best_text or path_fallback
    return chosen[:4000] if chosen else ""


def fetch_cited_text(
    repo_id: str,
    file_path: str,
    start_line: int,
    end_line: int,
    *,
    retrieval_hits: list[dict[str, Any]] | None = None,
) -> str:
    """Read cited lines from clone, else overlapping chunk metadata / retrieval hits."""
    from app.agent.confidence import _clone_file_path, _load_repo_metadata, _normalize_repo_path

    norm = path_key(file_path)
    s = max(1, int(start_line))
    e = max(s, int(end_line))
    abs_path = _clone_file_path(repo_id, _normalize_repo_path(file_path))
    if abs_path is not None and abs_path.is_file():
        try:
            lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines()
            e = min(len(lines), e)
            if s <= e:
                return "\n".join(lines[s - 1 : e])
        except OSError:
            pass

    best_overlap = 0
    best_text = ""
    for meta in _load_repo_metadata(repo_id):
        meta_path = path_key(
            str(meta.get("display_path") or meta.get("file_path") or meta.get("normalized_path") or "")
        )
        if meta_path != norm:
            continue
        chunk_start = int(meta.get("start_line") or 0)
        chunk_end = int(meta.get("end_line") or chunk_start)
        overlap = max(0, min(e, chunk_end) - max(s, chunk_start) + 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = str(meta.get("chunk") or meta.get("snippet") or "")

    if best_text:
        return best_text[:4000]

    from_hits = _retrieval_text_for_citation(norm, s, e, retrieval_hits)
    if from_hits:
        return from_hits
    return _retrieval_text_for_citation(norm, s, e, retrieval_hits, path_only=True)


def _lexical_overlap_score(claim: str, cited_text: str) -> float:
    """Token overlap — natural-language claims vs code often score low on embeddings alone."""
    claim_tokens = {
        t for t in re.findall(r"[a-zA-Z_][\w]*", claim.lower()) if len(t) > 2
    }
    code_tokens = {
        t for t in re.findall(r"[a-zA-Z_][\w]*", cited_text.lower()) if len(t) > 2
    }
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & code_tokens) / len(claim_tokens)


def _line_range_ok(
    citation: dict[str, Any],
    repo_id: str,
    *,
    allowed_paths: set[str] | None = None,
) -> bool:
    """True when cited lines overlap an indexed chunk or pass strict bounds."""
    from app.agent.confidence import (
        _load_repo_metadata,
        path_key,
    )

    cite = {**citation, "repo_id": repo_id, "function_name": None, "unparseable": False}
    if check_line_bounds(cite):
        return True

    path = path_key(str(citation.get("file_path", "")))
    start = int(citation.get("start_line") or 0)
    end = int(citation.get("end_line") or start)
    if not path or start < 1:
        return False

    for meta in _load_repo_metadata(repo_id):
        meta_path = path_key(
            str(meta.get("display_path") or meta.get("file_path") or meta.get("normalized_path") or "")
        )
        if meta_path != path:
            continue
        cs = int(meta.get("start_line") or 0)
        ce = int(meta.get("end_line") or cs)
        if start <= ce and end >= cs:
            return True

    return False


def _structural_ok(
    citation: dict[str, Any],
    repo_id: str,
    *,
    allowed_paths: set[str] | None = None,
) -> bool:
    from app.agent.confidence import check_file_existence, path_key

    raw_path = str(citation.get("file_path", ""))
    pk = path_key(raw_path)
    cite = {
        **citation,
        "file_path": _normalize_repo_path(raw_path),
        "repo_id": repo_id,
        "function_name": None,
        "unparseable": False,
    }
    path_ok = (
        check_file_existence(cite)
        or (allowed_paths is not None and pk in allowed_paths)
    )
    lines_ok = _line_range_ok(citation, repo_id, allowed_paths=allowed_paths)
    return path_ok and lines_ok


def _log_verify_check(
    *,
    repo_id: str,
    claim_index: int,
    claim_text: str,
    citation: dict[str, Any] | None,
    structural_ok: bool,
    cited_text_len: int,
    supported: bool | None,
    method: str,
    similarity: float | None = None,
    lookup_note: str = "",
) -> None:
    logger.info(
        "claim_verify_check",
        repo_id=repo_id,
        claim_index=claim_index,
        claim_preview=(claim_text or "")[:120],
        citation_file=citation.get("file_path") if citation else None,
        citation_lines=(
            f"{citation.get('start_line')}-{citation.get('end_line')}"
            if citation and citation.get("start_line")
            else None
        ),
        structural_ok=structural_ok,
        cited_text_len=cited_text_len,
        supported=supported,
        method=method,
        similarity=similarity,
        lookup_note=lookup_note,
    )


def _normalize_repo_path(path: str) -> str:
    from app.agent.confidence import _normalize_repo_path as _nrp
    return _nrp(path)


def _verify_embedding_batch(
    pairs: list[tuple[str, str]],
) -> list[float]:
    """Return cosine similarity for each (claim, cited_text) pair."""
    if not pairs:
        return []
    try:
        from app.retrieval.embeddings import embed_batch

        texts = [p[0] for p in pairs] + [p[1] for p in pairs]
        vectors = embed_batch(texts)
        n = len(pairs)
        scores: list[float] = []
        for i in range(n):
            scores.append(_cosine_similarity(vectors[i], vectors[n + i]))
        return scores
    except Exception as exc:
        logger.warning("claim_embed_verify_failed", error=str(exc))
        return [0.0] * len(pairs)


def _verify_llm_batch(
    items: list[dict[str, Any]],
) -> list[bool]:
    """
    Single batched Groq call: yes/no per claim against cited text.
    """
    if not items:
        return []

    lines = []
    for i, item in enumerate(items):
        lines.append(
            f"[{i}] CLAIM: {item['claim']}\n"
            f"CITED CODE:\n{item['cited_text'][:1500]}\n"
        )
    prompt = (
        "For each numbered item, answer whether the CLAIM is directly supported by "
        "the CITED CODE (not general knowledge). "
        'Return JSON only: {"results": [{"index": 0, "supported": true}, ...]}\n\n'
        + "\n".join(lines)
    )
    try:
        from app.agent.llm_client import get_llm_client

        llm = get_llm_client()
        raw = llm.generate_text(prompt)
        payload = json.loads(strip_json_fences(raw))
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return [False] * len(items)
        supported = [False] * len(items)
        for row in results:
            if not isinstance(row, dict):
                continue
            idx = row.get("index")
            if isinstance(idx, int) and 0 <= idx < len(items):
                supported[idx] = bool(row.get("supported"))
        return supported
    except Exception as exc:
        logger.warning("claim_llm_verify_failed", error=str(exc))
        return [False] * len(items)


def verify_claims_batch(
    claims: list[dict[str, Any]],
    repo_id: str,
    *,
    retrieval_hits: list[dict[str, Any]] | None = None,
    allowed_paths: set[str] | None = None,
) -> dict[str, Any]:
    """
    Verify all claims in one batched pass.

    Returns:
        {
          "results": [{index, supported, structural_ok, similarity, method}, ...],
          "verified_count": int,
          "factual_count": int,
          "latency_ms": float,
        }
    """
    t0 = time.perf_counter()
    threshold = float(getattr(settings, "CLAIM_EMBED_THRESHOLD", 0.40))
    borderline_low = threshold - 0.08
    lexical_threshold = float(getattr(settings, "CLAIM_LEXICAL_THRESHOLD", 0.18))
    use_llm = bool(getattr(settings, "CLAIM_VERIFY_LLM_BATCH", False))

    results: list[dict[str, Any]] = []
    embed_pairs: list[tuple[str, str]] = []
    embed_indices: list[int] = []
    llm_items: list[dict[str, Any]] = []
    llm_indices: list[int] = []
    cited_text_lens: dict[int, int] = {}

    for i, claim in enumerate(claims):
        if is_abstention_claim(claim):
            results.append({
                "index": i,
                "supported": True,
                "structural_ok": True,
                "similarity": None,
                "method": "abstention",
            })
            continue

        citation = claim.get("citation")
        if not citation:
            results.append({
                "index": i,
                "supported": False,
                "structural_ok": False,
                "similarity": None,
                "method": "missing_citation",
            })
            continue

        structural = _structural_ok(citation, repo_id, allowed_paths=allowed_paths)
        if not structural:
            results.append({
                "index": i,
                "supported": False,
                "structural_ok": False,
                "similarity": None,
                "method": "structural_fail",
            })
            continue

        cite_start = int(citation["start_line"])
        cite_end = int(citation.get("end_line") or cite_start)
        cited_text = fetch_cited_text(
            repo_id,
            citation["file_path"],
            cite_start,
            cite_end,
            retrieval_hits=retrieval_hits,
        )
        if not cited_text.strip():
            cited_text = _retrieval_text_for_citation(
                path_key(str(citation.get("file_path", ""))),
                cite_start,
                cite_end,
                retrieval_hits,
                path_only=True,
            )
        if not cited_text.strip():
            results.append({
                "index": i,
                "supported": False,
                "structural_ok": True,
                "similarity": 0.0,
                "method": "empty_cited_text",
            })
            continue

        cited_text_lens[i] = len(cited_text)
        embed_pairs.append((str(claim.get("claim") or ""), cited_text))
        embed_indices.append(i)
        results.append({
            "index": i,
            "supported": False,
            "structural_ok": True,
            "similarity": None,
            "method": "pending",
            "_cited_text": cited_text,
        })

    # Embedding batch
    scores = _verify_embedding_batch(embed_pairs)
    for claim_idx, sim in zip(embed_indices, scores):
        row = next(r for r in results if r["index"] == claim_idx)
        row["similarity"] = round(sim, 4)
        if sim >= threshold:
            row["supported"] = True
            row["method"] = "embedding"
            row.pop("_cited_text", None)
        elif use_llm and sim >= borderline_low:
            llm_items.append({
                "claim": claims[claim_idx].get("claim"),
                "cited_text": row.pop("_cited_text", ""),
            })
            llm_indices.append(claim_idx)
        else:
            cited_text = row.pop("_cited_text", "")
            lex = _lexical_overlap_score(str(claims[claim_idx].get("claim") or ""), cited_text)
            if lex >= lexical_threshold:
                row["supported"] = True
                row["method"] = "lexical"
            else:
                row["supported"] = False
                row["method"] = "embedding"

    # Optional single LLM batch for borderline / configured mode
    if llm_items:
        llm_supported = _verify_llm_batch(llm_items)
        for claim_idx, ok in zip(llm_indices, llm_supported):
            row = next(r for r in results if r["index"] == claim_idx)
            row["supported"] = ok
            row["method"] = "llm_batch"
            row.pop("_cited_text", None)

    # Per-claim debug audit trail
    for i, claim in enumerate(claims):
        row = next((r for r in results if r["index"] == i), None)
        if not row:
            continue
        _log_verify_check(
            repo_id=repo_id,
            claim_index=i,
            claim_text=str(claim.get("claim") or ""),
            citation=claim.get("citation"),
            structural_ok=bool(row.get("structural_ok")),
            cited_text_len=cited_text_lens.get(i, 0),
            supported=row.get("supported"),
            method=str(row.get("method", "")),
            similarity=row.get("similarity"),
        )

    # Clean internal fields
    for row in results:
        row.pop("_cited_text", None)

    factual_count = sum(1 for c in claims if is_factual_claim(c))
    verified_count = sum(
        1 for r in results
        if r.get("supported") and claims[r["index"]].get("citation") is not None
        and not is_abstention_claim(claims[r["index"]])
    )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "claim_verify_batch_complete",
        repo_id=repo_id,
        factual_count=factual_count,
        verified_count=verified_count,
        latency_ms=elapsed_ms,
    )

    return {
        "results": results,
        "verified_count": verified_count,
        "factual_count": factual_count,
        "latency_ms": elapsed_ms,
    }
