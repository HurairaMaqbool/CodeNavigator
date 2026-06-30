"""
app/retrieval/hybrid_search.py
------------------------------
Hybrid retrieval combining vector semantic search and BM25 keyword search.

Responsibility boundary
-----------------------
This module queries both indexes independently and merges the candidate lists
using Reciprocal Rank Fusion (RRF).
It does NOT:
  - run cross-encoder reranking (Module 6b),
  - perform query expansion (Module 6b),
  - enforce diversity max-per-file caps (Module 6b).

Why Reciprocal Rank Fusion (RRF)?
---------------------------------
RRF score = sum(1 / (k + rank_i)) across all lists where the item appears.
Vector scores (cosine similarity) and BM25 scores are on completely different
numeric scales.  Attempting to merge them with a weighted average (e.g.
0.7 * vector + 0.3 * BM25) is brittle: it silently biases toward whichever
metric happens to have a wider range, and requires re-tuning every time the
embedding model changes.
RRF is rank-based, meaning it is scale-invariant. It guarantees that an item
ranking highly in both lists will consistently beat an item ranking highly in
only one, regardless of the underlying raw score magnitudes.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from app.config import settings
from app.observability.logging_config import logger
from app.retrieval.bm25_store import BM25SearchResult, search_bm25
from app.retrieval.vector_store import VectorSearchResult, search_vectors

# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------

@dataclass
class FusedCandidate:
    """A single deduplicated hit resulting from RRF fusion."""
    id: str
    rrf_score: float
    document: str
    metadata: dict[str, Any]
    vector_rank: int | None
    bm25_rank: int | None


# ---------------------------------------------------------------------------
# RRF Implementation
# ---------------------------------------------------------------------------

def search_hybrid(
    repo_id: str,
    query: str,
    n_results: int = 20,
) -> list[FusedCandidate]:
    """
    Execute a hybrid search for *query* on *repo_id*, returning up to
    *n_results* RRF-fused candidates.

    Algorithm
    ---------
    1. Query vector store for top N.
    2. Query BM25 store for top N.
    3. For each hit across both lists, compute RRF score:
       `score = 0`
       `if in vector: score += 1 / (k + vector_rank)`
       `if in bm25:   score += 1 / (k + bm25_rank)`
    4. Sort by RRF score descending.

    Parameters
    ----------
    repo_id:
        The repository identifier.
    query:
        The raw search string.
    n_results:
        The number of results to fetch from EACH store independently,
        and the maximum number of fused results to return.

    Returns
    -------
    list[FusedCandidate]
        Sorted by rrf_score descending.
    """
    log = logger.bind(repo_id=repo_id)
    start_time = time.perf_counter()

    # 1. Fetch independent lists
    #    Both return empty lists if their respective store doesn't exist.
    v_results = search_vectors(repo_id, query, n_results=n_results)
    b_results = search_bm25(repo_id, query, top_n=n_results)

    log.debug(
        "hybrid_search_raw_hits",
        vector_hits=len(v_results),
        bm25_hits=len(b_results),
    )

    if not v_results and not b_results:
        return []

    # 2. RRF Fusion
    k = settings.RRF_K

    # Use a dict to deduplicate by chunk ID
    candidates: dict[str, FusedCandidate] = {}

    # Helper to merge a hit into the FusedCandidate dict
    def _merge_hit(
        _id: str,
        _doc: str,
        _meta: dict[str, Any],
        _v_rank: int | None = None,
        _b_rank: int | None = None,
    ):
        if _id not in candidates:
            candidates[_id] = FusedCandidate(
                id=_id,
                rrf_score=0.0,
                document=_doc,
                metadata=_meta,
                vector_rank=None,
                bm25_rank=None,
            )
        cand = candidates[_id]
        if _v_rank is not None:
            cand.vector_rank = _v_rank
            cand.rrf_score += 1.0 / (k + _v_rank)
        if _b_rank is not None:
            cand.bm25_rank = _b_rank
            cand.rrf_score += 1.0 / (k + _b_rank)

    # Note: rank is 1-indexed for RRF
    for i, v in enumerate(v_results):
        _merge_hit(v.id, v.document, v.metadata, _v_rank=i + 1)

    for i, b in enumerate(b_results):
        _merge_hit(b.id, b.document, b.metadata, _b_rank=i + 1)

    # 3. Sort by combined RRF score descending
    sorted_candidates = sorted(
        candidates.values(),
        key=lambda c: c.rrf_score,
        reverse=True,
    )

    # Trim to final top K
    final_list = sorted_candidates[:n_results]

    log.info(
        "hybrid_search_fused",
        query_len=len(query),
        fused_total=len(candidates),
        returned=len(final_list),
        time_ms=round((time.perf_counter() - start_time) * 1000, 2),
    )

    return final_list


# ---------------------------------------------------------------------------
# Final Assembly (Module 6b)
# ---------------------------------------------------------------------------

def dedup_by_file(
    reranked: list[dict],
    max_per_file: int = 2,
) -> list[dict]:
    """
    Enforce a diversity cap on the reranked candidate list.
    
    Prevents a single large, broadly relevant file from crowding out the
    entire top-K context window. If a file has more than `max_per_file`
    chunks in the list, the lower-ranked ones are dropped.
    """
    file_counts: dict[str, int] = {}
    capped: list[dict] = []

    for item in reranked:
        path = item["metadata"].get("normalized_path") or item["metadata"].get("file_path") or item["metadata"].get("display_path") or "unknown"
        count = file_counts.get(path, 0)
        
        if count < max_per_file:
            capped.append(item)
            file_counts[path] = count + 1

    return capped


def search_code(
    query: str,
    repo_id: str,
    llm: Any,  # Protocol matched against LLMClient in query_expansion
    top_k: int = 5,
    max_per_file: int = 2,
) -> list[dict]:
    """
    The primary retrieval entry point for the agent loop.

    Pipeline:
    1. Query Expansion (gated by heuristic).
    2. Hybrid Search (Vector + BM25) for each sub-query.
    3. Candidate deduplication across sub-queries.
    4. RRF Fusion (handled inside search_hybrid, though we accumulate across queries here).
    5. Cross-Encoder Reranking (top 20 only).
    6. Diversity Capping (max 2 per file).
    7. Final slice to `top_k`.

    Returns
    -------
    list[dict]
        Format exactly matching Module 9's expectation:
        [{"chunk": "<text>", "metadata": {...}, "rerank_score": 0.83}, ...]
    """
    from app.retrieval.query_expansion import needs_expansion, expand_query
    from app.retrieval.reranker import cross_encoder_rerank

    log = logger.bind(repo_id=repo_id)

    # 1. Query Expansion
    if settings.QUERY_EXPANSION_ENABLED and needs_expansion(query):
        sub_queries = expand_query(query, llm)
    else:
        sub_queries = [query]

    # 2 & 3 & 4. Hybrid Search per sub-query
    # We fetch a larger pool across all sub-queries and fuse them.
    all_fused_candidates: dict[str, FusedCandidate] = {}
    
    for sq in sub_queries:
        # We ask for a healthy top_n from the hybrid pass for each subquery
        sq_candidates = search_hybrid(repo_id, sq, n_results=20)
        
        for cand in sq_candidates:
            if cand.id not in all_fused_candidates:
                all_fused_candidates[cand.id] = cand
            else:
                # If a chunk appears in multiple sub-queries, keep its max RRF score
                existing = all_fused_candidates[cand.id]
                if cand.rrf_score > existing.rrf_score:
                    all_fused_candidates[cand.id] = cand

    # Sort merged RRF pool
    merged_list = sorted(
        all_fused_candidates.values(),
        key=lambda c: c.rrf_score,
        reverse=True
    )
    
    # 5. Cross-Encoder Reranking
    # We MUST ONLY run the cross-encoder on the top 20, regardless of how many
    # candidates bubbled up from the sub-queries. This is a strict performance bound.
    top_20 = merged_list[:20]
    reranked = cross_encoder_rerank(query, top_20)

    # 6. Diversity Capping
    capped = dedup_by_file(reranked, max_per_file=max_per_file)

    # 7. Final Slice
    final_list = capped[:top_k]

    log.info(
        "search_code_completed",
        queries_run=len(sub_queries),
        candidates_fused=len(merged_list),
        candidates_reranked=len(top_20),
        returned=len(final_list)
    )

    return final_list
