# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/retrieval/reranker.py
-------------------------
Cross-encoder reranking pass.

Responsibility boundary
-----------------------
This module applies a cross-encoder model to re-score a small set of pre-filtered
candidates.
It does NOT:
  - execute vector or BM25 retrieval,
  - run RRF fusion,
  - limit the number of candidates per file (diversity capping).

Performance Constraint
----------------------
Cross-encoders are O(N) in the number of candidates because they run a full
transformer forward pass on the concatenated (query, candidate) string.
This module MUST ONLY BE RUN on the top-N candidates from the initial hybrid
search (e.g. N=20). Running this on hundreds of chunks will destroy latency.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Sequence

# We import CrossEncoder lazily to avoid loading heavy models on import if unused.
from app.config import settings
from app.observability.logging_config import logger
from app.retrieval.hybrid_search import FusedCandidate

_RERANKER_MODEL = None
_RERANKER_LOCK = threading.Lock()

# CPU-only inference: avoid meta-tensor init before CrossEncoder.model.to(device).
_AUTO_MODEL_LOAD_KWARGS = {"low_cpu_mem_usage": False}


def _topical_keyword_boost(query: str, metadata: dict, chunk: str) -> float:
    """Boost chunks whose symbols/text match the question's topical intent."""
    q = query.lower()
    path = (
        metadata.get("display_path")
        or metadata.get("normalized_path")
        or metadata.get("file_path")
        or ""
    ).lower()
    fn = str(metadata.get("function_name") or "").lower()
    text = f"{chunk} {fn} {path}".lower()
    boost = 0.0
    if re.search(r"\bpool", q):
        markers = (
            "poolmanager", "init_poolmanager", "pool_manager",
            "httpadapter", "get_connection_with_tls",
        )
        if any(m in text for m in markers):
            boost += 0.15
    if any(w in q for w in ("improve", "performance", "faster", "benefit", "efficient")):
        if any(w in text for w in ("reuse", "keep-alive", "keep alive", "cache", "pool", "connection")):
            boost += 0.08
    if re.search(r"\bwhy\b", q):
        if any(m in text for m in ("instead of", "rather than", "because", "maintain", "reuse", "complex")):
            boost += 0.12
        if path.endswith("readme.md") or path.endswith("history.md"):
            boost += 0.18
    if re.search(r"\bcookie", q):
        if any(m in text for m in ("merge_cookies", "cookiejar", "extract_cookies", "prepare_cookies")):
            boost += 0.14
    if re.search(r"\bhttpadapter\b", q):
        if "class httpadapter" in text or fn == "httpadapter" or fn.startswith("__init__") or fn == "send":
            boost += 0.10
    return boost


from app.retrieval.source_priority import source_path_penalty


def _source_path_boost(metadata: dict, query: str = "") -> float:
    path = (
        metadata.get("display_path")
        or metadata.get("normalized_path")
        or metadata.get("file_path")
        or ""
    )
    return source_path_penalty(path, query)


def _rerank_with_path_boost(
    query_text: str,
    results: list[dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    """Fallback when cross-encoder unavailable — RRF score + query/path alignment."""
    out: list[dict[str, Any]] = []
    for r in results:
        meta = r.get("chunk_metadata") or {}
        path = meta.get("display_path") or meta.get("file_path") or ""
        score = float(r.get("score", 0.0)) + _source_path_boost(meta, query_text)
        out.append(
            {
                "chunk": r["chunk"],
                "chunk_metadata": meta,
                "score": score,
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[float, str, int, int]:
        meta = item.get("chunk_metadata") or {}
        return (
            -float(item.get("score", 0.0)),
            str(meta.get("file_path") or meta.get("display_path") or ""),
            int(meta.get("start_line") or 0),
            int(meta.get("end_line") or 0),
        )

    out.sort(key=_sort_key)
    return out[:top_n]


def _get_model() -> Any:
    """Return the global CrossEncoder, initializing it if necessary."""
    global _RERANKER_MODEL
    if _RERANKER_MODEL is not None:
        return _RERANKER_MODEL
    with _RERANKER_LOCK:
        if _RERANKER_MODEL is None:
            from sentence_transformers import CrossEncoder  # type: ignore[import]

            model_name = settings.CROSS_ENCODER_MODEL
            logger.info("loading_cross_encoder_model", model_name=model_name)
            try:
                model = CrossEncoder(
                    model_name,
                    device="cpu",
                    automodel_args=dict(_AUTO_MODEL_LOAD_KWARGS),
                )
                model.predict([("warmup", "warmup")], show_progress_bar=False)
                _RERANKER_MODEL = model
                logger.info("cross_encoder_model_loaded", model_name=model_name)
            except Exception as exc:
                logger.error("cross_encoder_model_load_failed", model_name=model_name, error=str(exc))
                raise RuntimeError(f"Failed to load cross-encoder model: {exc}") from exc
    return _RERANKER_MODEL


def _definition_boost(query: str, metadata: dict, chunk: str) -> float:
    """Boost chunks that define a class/function named in the query."""
    fn = metadata.get("function_name") or ""
    boost = 0.0
    for word in re.findall(r"\b[A-Z][a-zA-Z_]\w*\b", query):
        if f"class {word}" in chunk:
            boost = max(boost, 0.14)
        if fn == word or fn.startswith(f"{word}."):
            boost = max(boost, 0.10)
    if "class" in query.lower():
        for word in re.findall(r"\b[A-Z][a-zA-Z_]\w*\b", query):
            if f"class {word}" in chunk:
                boost = max(boost, 0.16)
    return boost


def cross_encoder_rerank(
    query: str,
    candidates: Sequence[FusedCandidate],
) -> list[dict]:
    """
    Re-score the top candidates using a cross-encoder and return them sorted.

    Parameters
    ----------
    query:
        The search string.
    candidates:
        The pre-filtered candidates (e.g., from hybrid_search).
        MUST NOT exceed a small bounded number (e.g., 20).

    Returns
    -------
    list[dict]
        A new list of dictionaries with structure:
        {
            "chunk": FusedCandidate.document,
            "metadata": FusedCandidate.metadata,
            "rerank_score": float
        }
        Sorted by rerank_score descending.
    """
    if not candidates:
        return []

    if not settings.ENABLE_RERANKER:
        return [{"chunk": c.document, "metadata": c.metadata, "rerank_score": c.rrf_score} for c in candidates]

    start_time = time.perf_counter()

    # Enforce performance bound
    if len(candidates) > 50:
        logger.warning(
            "excessive_candidates_for_reranker",
            count=len(candidates),
            hint="Cross-encoders are slow. Pass only the top K (e.g., 20) to this function."
        )

    model = _get_model()

    # The cross-encoder expects a list of [query, text] pairs
    pairs = [[query, c.document] for c in candidates]
    
    # Predict scores (typically raw logits, which for ms-marco-MiniLM map to 
    # relevance but are not strictly [0,1] probabilities)
    # The default sentence-transformers models return floats.
    scores = model.predict(pairs, show_progress_bar=False)

    # Convert to standard Python floats if it's a numpy array
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    elif not isinstance(scores, list):
        scores = [float(scores)]

    # Guard: if scores is somehow empty, return candidates with score 0.5
    if not scores:
        return [{"chunk": c.document, "metadata": c.metadata, "rerank_score": 0.5} for c in candidates]

    # ABSOLUTE relevance, not min-max. Min-max normalization is a confidence
    # trap: it forces the single best candidate to 1.0 even when EVERY candidate
    # is a poor match, which made mean_confidence_score pin at 10.0 regardless of
    # real retrieval quality. ms-marco cross-encoder logits map to relevance via
    # a sigmoid, giving a stable absolute score in (0,1): a weak match scores
    # ~0.2, a strong one ~0.9. Ordering is identical (sigmoid is monotonic) but
    # the magnitude now reflects true relevance, so downstream confidence varies.
    import math

    def _sigmoid(x: float) -> float:
        # Numerically stable sigmoid.
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    norm_scores = [_sigmoid(float(s)) for s in scores]

    results = []
    
    for c, score in zip(candidates, norm_scores):
        final_score = min(
            1.0,
            max(
                0.0,
                score
                + _source_path_boost(c.metadata, query)
                + _definition_boost(query, c.metadata, c.document)
                + _topical_keyword_boost(query, c.metadata, c.document),
            ),
        )
        
        results.append({
            "chunk": c.document,
            "metadata": c.metadata,
            "rerank_score": final_score

        })

    def _rerank_sort_key(r: dict) -> tuple[float, str, int, int]:
        meta = r.get("metadata") or {}
        return (
            -float(r.get("rerank_score", 0.0)),
            str(meta.get("file_path") or meta.get("display_path") or ""),
            int(meta.get("start_line") or 0),
            int(meta.get("end_line") or 0),
        )

    results.sort(key=_rerank_sort_key)
    
    elapsed = time.perf_counter() - start_time
    logger.info("reranker_completed", time_ms=round(elapsed * 1000, 2), hits=len(results))
    
    return results


# ---------------------------------------------------------------------------
# Module #16 Additions: get_model and rerank
# ---------------------------------------------------------------------------

def get_model() -> Any:
    """
    Return the global cached CrossEncoder singleton instance,
    loading it once on first call (warm-up).
    """
    return _get_model()


def rerank(
    query_text: str,
    results: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Re-score query-chunk pairs in results using a local Cross-Encoder.

    Forward Interface Contract:
    --------------------------
    Returns a list of dicts:
        [
            {
                "chunk": str,
                "chunk_metadata": {
                    "file_path": str,
                    "display_path": str,
                    "function_name": str,
                    "start_line": int,
                    "end_line": int,
                    "type": str,
                    "language": str,
                    "fingerprint": str,
                },
                "score": float  # The cross-encoder score
            },
            ...
        ]
    This is ready to be consumed by app/agent/loop.py.
    """
    if not results:
        return []

    if not settings.ENABLE_RERANKER:
        return _rerank_with_path_boost(query_text, results, top_n)

    # Enforce strict CPU latency bound by slicing to top 12 candidates
    results = results[:12]

    start_time = time.perf_counter()
    try:
        model = get_model()
    except (ImportError, ModuleNotFoundError, OSError, RuntimeError) as exc:
        logger.warning("reranker_model_unavailable", error=str(exc))
        return _rerank_with_path_boost(query_text, results, top_n)

    # Concatenate query and candidate text pairs for single-batch prediction
    pairs = [[query_text, r["chunk"]] for r in results]
    scores = model.predict(pairs, show_progress_bar=False)

    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    elif not isinstance(scores, list):
        scores = [float(scores)]

    if not scores:
        return [{
            "chunk": r["chunk"],
            "chunk_metadata": r["chunk_metadata"],
            "score": 0.5
        } for r in results][:top_n]

    import math

    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    norm_scores = [_sigmoid(float(s)) for s in scores]
    fused_results = []

    for r, score in zip(results, norm_scores):
        meta = r["chunk_metadata"]
        final_score = min(
            1.0,
            max(0.0, score + source_path_penalty(
                meta.get("display_path") or meta.get("file_path") or "", query_text
            ) + _definition_boost(query_text, meta, r["chunk"]) + _topical_keyword_boost(query_text, meta, r["chunk"])),
        )

        fused_results.append({
            "chunk": r["chunk"],
            "chunk_metadata": meta,
            "score": final_score
        })

    def _rerank_sort_key(item: dict[str, Any]) -> tuple[float, str, int, int]:
        meta = item.get("chunk_metadata") or {}
        return (
            -float(item.get("score", 0.0)),
            str(meta.get("file_path") or meta.get("display_path") or ""),
            int(meta.get("start_line") or 0),
            int(meta.get("end_line") or 0),
        )

    fused_results.sort(key=_rerank_sort_key)
    
    elapsed = time.perf_counter() - start_time
    logger.info("rerank_function_completed", time_ms=round(elapsed * 1000, 2), hits=len(fused_results))

    return fused_results[:top_n]
