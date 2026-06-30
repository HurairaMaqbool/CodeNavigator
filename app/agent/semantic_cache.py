"""
app/agent/semantic_cache.py
---------------------------
Semantic Answer Cache for the RAG pipeline.

Responsibility boundary
-----------------------
Wraps the entire `answer_question` pipeline to short-circuit repeated or
semantically identical questions.
It does NOT:
  - implement the pipeline itself (Module 9a/9b)
  - cache RAG context or retrieval hits independently

Why strict CACHE_SIMILARITY_THRESHOLD cosine similarity?
----------------------------------
A false-positive cache hit — two genuinely different questions served the same
cached answer — erodes user trust in a way a slow cache miss never does. A miss
just costs latency; a wrong hit costs correctness silently. We err toward fewer
false positives.

Why wipe the cache on EMBEDDING_MODEL changes?
----------------------------------------------
If the embedding model changes, the vector space fundamentally shifts. A cosine similarity in one space is meaningless in another. Rather than trying to
reconcile, we wipe and rebuild (mirroring Module 6a's force_reindex semantics)
to prevent stale cache queries from matching garbage.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import chromadb  # type: ignore[import]

from app.chroma_client import chroma_settings
from app.agent.system_prompt import PROMPT_VERSION
from app.config import settings
from app.observability.logging_config import logger

# Modules 9a+9b combined via `answer_question` and `validate_and_return`
# We import loop directly, which internally calls validation in 9b.
# But wait, Module 9a's `answer_question` calls `validate_and_return`.
from app.agent.loop import answer_question
from app.retrieval.embeddings import embed

_STATS = {"hits": 0, "misses": 0, "expired": 0}


# ---------------------------------------------------------------------------
# Storage Backend
# ---------------------------------------------------------------------------

def _get_cache_collection(repo_id: str) -> chromadb.Collection | None:
    """
    Get the ChromaDB collection for this repo's semantic cache.
    Recreates the collection if the EMBEDDING_MODEL has changed.
    """
    # Use persistent client pointing to CHROMA_DB_PATH
    try:
        client = chromadb.PersistentClient(
            path=settings.CHROMA_DB_PATH,
            settings=chroma_settings(),
        )
    except Exception as e:
        logger.error("semantic_cache_chroma_init_failed", error=str(e))
        return None

    collection_name = f"{repo_id[:50]}_answer_cache"
    
    # Check if we need to wipe due to model change
    try:
        col = client.get_collection(collection_name)
        # Check metadata
        raw_meta = col.metadata
        if raw_meta is None:
            col_meta: dict[str, Any] = {}
        elif isinstance(raw_meta, dict):
            col_meta = raw_meta
        else:
            try:
                col_meta = dict(raw_meta)
            except Exception:
                col_meta = {}
        stored_model = col_meta.get("embedding_model_id")
        stored_prompt = col_meta.get("prompt_version")
        from app.agent.system_prompt import PROMPT_VERSION
        if stored_model and stored_model != settings.EMBEDDING_MODEL:
            logger.warning("semantic_cache_model_mismatch", 
                           stored=stored_model, current=settings.EMBEDDING_MODEL)
            client.delete_collection(collection_name)
            col = None
        elif stored_prompt and stored_prompt != PROMPT_VERSION:
            logger.warning(
                "semantic_cache_prompt_mismatch",
                stored=stored_prompt,
                current=PROMPT_VERSION,
            )
            client.delete_collection(collection_name)
            col = None
    except chromadb.errors.InvalidCollectionException:
        col = None
        
    if col is None:
        try:
            from app.agent.system_prompt import PROMPT_VERSION
            col = client.create_collection(
                name=collection_name,
                metadata={
                    "embedding_model_id": settings.EMBEDDING_MODEL,
                    "prompt_version": PROMPT_VERSION,
                    "hnsw:space": "cosine" # Crucial: cosine space so distance = 1 - sim
                }
            )
        except Exception as e:
            logger.error("semantic_cache_collection_create_failed", error=str(e))
            return None
            
    return col


# ---------------------------------------------------------------------------
# Cache Operations
# ---------------------------------------------------------------------------

class SemanticCache:
    @staticmethod
    def get_cache_stats(repo_id: str) -> dict[str, Any]:
        col = _get_cache_collection(repo_id)
        total_entries = col.count() if col else 0
        total_requests = _STATS["hits"] + _STATS["misses"]
        hit_rate = round(_STATS["hits"] / total_requests, 2) if total_requests > 0 else 0.0
        return {
            "total_entries": total_entries,
            "hit_rate": hit_rate,
            "expired_entries": _STATS["expired"],
            "session_hits": _STATS["hits"],
            "session_misses": _STATS["misses"]
        }

    @staticmethod
    def invalidate_old_commits(repo_id: str, current_commit: str) -> None:
        col = _get_cache_collection(repo_id)
        if not col:
            return
        try:
            col.delete(where={"repo_commit_hash": {"$ne": current_commit}})
            logger.info("semantic_cache_invalidated_old_commits", repo_id=repo_id, current_commit=current_commit)
        except Exception as e:
            logger.error("semantic_cache_invalidate_failed", error=str(e))

    @staticmethod
    def find_nearest(repo_id: str, query_embedding: list[float], threshold: float | None = None) -> dict[str, Any] | None:
        if threshold is None:
            threshold = settings.CACHE_SIMILARITY_THRESHOLD
            
        col = _get_cache_collection(repo_id)
        if not col:
            return None
        count = col.count()
        if isinstance(count, int) and count == 0:
            return None
            
        try:
            results = col.query(
                query_embeddings=[query_embedding],
                n_results=1
            )
        except Exception as e:
            logger.warning("semantic_cache_query_failed", error=str(e))
            return None
            
        if not results["ids"] or not results["ids"][0]:
            return None

        distances = results.get("distances")
        if not distances or not distances[0]:
            return None

        distance = float(distances[0][0])
        similarity = 1.0 - distance
        
        if similarity > threshold:
            meta = results["metadatas"][0][0]
            
            # TTL check
            cached_at = meta.get("timestamp", 0)
            ttl_seconds = settings.SEMANTIC_CACHE_TTL_DAYS * 86400
            if int(time.time()) - cached_at > ttl_seconds:
                try:
                    col.delete(ids=[results["ids"][0][0]])
                    _STATS["expired"] += 1
                    logger.info("semantic_cache_entry_expired_and_deleted", repo_id=repo_id)
                except Exception:
                    pass
                return None
                
            try:
                answer_dict = json.loads(meta["answer_json"])
                return {
                    "answer": answer_dict,
                    "repo_commit_hash": meta["repo_commit_hash"],
                    "similarity": similarity
                }
            except Exception as e:
                logger.warning("semantic_cache_deserialize_failed", error=str(e))
                return None
                
        return None

    @staticmethod
    def store(repo_id: str, query_embedding: list[float], answer: dict[str, Any], repo_commit_hash: str) -> None:
        col = _get_cache_collection(repo_id)
        if not col:
            return
            
        entry_id = f"cache_{uuid.uuid4().hex}"
        
        try:
            col.add(
                ids=[entry_id],
                embeddings=[query_embedding],
                metadatas=[{
                    "answer_json": json.dumps(answer),
                    "repo_commit_hash": repo_commit_hash,
                    "timestamp": int(time.time())
                }]
            )
        except Exception as e:
            logger.warning("semantic_cache_store_failed", error=str(e))


def _get_repo_metadata(repo_id: str) -> dict[str, Any]:
    """Load repo metadata directly from the sync status file."""
    from pathlib import Path
    status_file = Path(settings.REPOS_PATH) / repo_id / "sync_status.json"
    if status_file.exists():
        try:
            return json.loads(status_file.read_text())
        except Exception:
            pass
    return {"commit_hash": ""}


# ---------------------------------------------------------------------------
# Cache hit refresh (re-apply post-processing after prompt/citation fixes)
# ---------------------------------------------------------------------------

def _refresh_cached_answer(cached: dict[str, Any], question: str, repo_id: str) -> dict[str, Any]:
    """Re-run prefetch + citation repair so cached answers use latest logic."""
    from app.agent.loop import _prefetch_context
    from app.agent.citation_repair import repair_answer_citations
    from app.agent.confidence import _build_sources_from_hits, _symbol_sources_from_text

    log = logger.bind(repo_id=repo_id)
    _, hits, _best = _prefetch_context(question, repo_id, log)
    answer = repair_answer_citations(
        cached.get("answer", ""),
        hits,
        repo_id=repo_id,
        question=question,
    )
    sources = _symbol_sources_from_text(repo_id, answer, question, max_sources=5)
    if not sources:
        sources = _build_sources_from_hits(hits, max_sources=5)
    out = dict(cached)
    out["answer"] = answer
    out["sources"] = sources
    out["retrieval_hits"] = hits
    return out


# ---------------------------------------------------------------------------
# Public Wrapper
# ---------------------------------------------------------------------------

def answer_question_cached(question: str, repo_id: str, **kwargs) -> dict[str, Any]:
    """
    Wraps the standard answer_question pipeline with a semantic answer cache.
    """
    # 1. Feature flag bypass
    if not settings.SEMANTIC_CACHE_ENABLED:
        result = answer_question(question, repo_id, **kwargs)
        return {**result, "cache_hit": False}
        
    log = logger.bind(repo_id=repo_id)
    repo_meta = _get_repo_metadata(repo_id)
    current_commit = repo_meta.get("commit_hash", "")
    
    # 2. Embed the question
    try:
        query_embedding = embed(question)
    except Exception as e:
        log.warning("semantic_cache_embed_failed", error=str(e))
        result = answer_question(question, repo_id, **kwargs)
        return {**result, "cache_hit": False}

    # 3. Check Cache
    cached = SemanticCache.find_nearest(
        repo_id, 
        query_embedding, 
        threshold=settings.CACHE_SIMILARITY_THRESHOLD
    )
    
    # Invalidation is commit-hash-based
    if cached:
        if cached["repo_commit_hash"] == current_commit:
            stored_prompt = cached.get("prompt_version") or cached.get("answer", {}).get("prompt_version")
            if stored_prompt and stored_prompt != PROMPT_VERSION:
                log.info("semantic_cache_stale_prompt", stored=stored_prompt, current=PROMPT_VERSION)
            else:
                log.info("semantic_cache_hit", similarity=cached["similarity"])
                _STATS["hits"] += 1
                hit_ans = _refresh_cached_answer(dict(cached["answer"]), question, repo_id)
                hit_ans["trace"] = []
                hit_ans.pop("iterations_used", None)
                return {**hit_ans, "cache_hit": True}
        else:
            # Hash mismatch => trigger invalidation of old commits
            SemanticCache.invalidate_old_commits(repo_id, current_commit)
            
    # 4. Cache Miss - Run the full pipeline
    _STATS["misses"] += 1
    log.info("semantic_cache_miss")
    result = answer_question(question, repo_id, **kwargs)
    
    # 5. Store if not gated and not an error/rate-limited response.
    # Storing a gated, rate-limited, or otherwise errored answer would poison
    # subsequent requests: the cache would replay the error on the next identical
    # question even after the rate limit has cleared.
    is_error = bool(result.get("error") or result.get("rate_limited") or result.get("timed_out"))
    if not result.get("gated") and not is_error:
        SemanticCache.store(
            repo_id=repo_id,
            query_embedding=query_embedding,
            answer=result,
            repo_commit_hash=current_commit
        )
        
    # cache_hit must be the absolute last key merged
    return {**result, "cache_hit": False}


# ---------------------------------------------------------------------------
# TTL Sweep
# ---------------------------------------------------------------------------

def sweep_expired_entries(repo_id: str) -> None:
    """
    Sweep cache entries older than SEMANTIC_CACHE_TTL_DAYS.
    Expected to be called by an ops script or cron via Module 12.
    """
    col = _get_cache_collection(repo_id)
    if not col:
        return
        
    cutoff_ts = int(time.time()) - (settings.SEMANTIC_CACHE_TTL_DAYS * 86400)
    
    try:
        # We fetch all, and delete the expired ones.
        # In a real heavy production setup we might use a WHERE clause if Chroma supports > on metadata
        # Chroma supports `$lt` in `where` filters.
        col.delete(
            where={"timestamp": {"$lt": cutoff_ts}}
        )
        logger.info("semantic_cache_sweep_complete", repo_id=repo_id, cutoff=cutoff_ts)
    except Exception as e:
        logger.error("semantic_cache_sweep_failed", error=str(e))
