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
import time
from typing import Any, Sequence

# We import CrossEncoder lazily to avoid loading heavy models on import if unused.
from app.config import settings
from app.observability.logging_config import logger
from app.retrieval.hybrid_search import FusedCandidate

_RERANKER_MODEL = None


def _source_path_boost(metadata: dict) -> float:
    """Prefer src/ over tests/ and docs/ for code QA retrieval."""
    path = (
        metadata.get("display_path")
        or metadata.get("normalized_path")
        or metadata.get("file_path")
        or ""
    ).replace("\\", "/").lower()
    if "/tests/" in path or path.startswith("tests/"):
        return -0.18
    if "/docs/" in path or path.startswith("docs/"):
        return -0.10
    if "/src/" in path or path.startswith("src/"):
        return 0.06
    return 0.0


def _get_model() -> Any:
    """Return the global CrossEncoder, initializing it if necessary."""
    global _RERANKER_MODEL
    if _RERANKER_MODEL is None:
        from sentence_transformers import CrossEncoder  # type: ignore[import]
        
        model_name = settings.CROSS_ENCODER_MODEL
        logger.info("loading_cross_encoder_model", model_name=model_name)
        # We explicitly don't pass a device so it auto-selects the optimal one
        _RERANKER_MODEL = CrossEncoder(model_name)
        logger.info("cross_encoder_model_loaded", model_name=model_name)
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
    
    import os
    now = time.time()
    
    for c, score in zip(candidates, norm_scores):
        file_path = c.metadata.get("file_path")
        recency_boost = 0.0
        
        if file_path and os.path.exists(file_path):
            try:
                mtime = os.path.getmtime(file_path)
                age_days = (now - mtime) / 86400.0
                
                # Apply up to +0.10 boost for files modified in the last 7 days.
                if age_days < 7.0:
                    recency_boost = 0.10 * (1.0 - (age_days / 7.0))
            except Exception:
                pass
                
        final_score = min(
            1.0,
            max(0.0, score + recency_boost + _source_path_boost(c.metadata) + _definition_boost(query, c.metadata, c.document)),
        )
        
        results.append({
            "chunk": c.document,
            "metadata": c.metadata,
            "rerank_score": final_score

        })

    # Sort descending by rerank_score
    results.sort(key=lambda r: r["rerank_score"], reverse=True)
    
    elapsed = time.perf_counter() - start_time
    logger.info("reranker_completed", time_ms=round(elapsed * 1000, 2), hits=len(results))
    
    return results
