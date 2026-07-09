# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/agent/semantic_cache.py
---------------------------
Module #24 — Pre-loop semantic answer cache (INTAKE / RESPOND).

Embeds questions via ``app.retrieval.embeddings.embed`` and compares with cosine
similarity in Chroma (``hnsw:space=cosine``, same metric family as vector_store).

Zero Groq/LLM cost in this module — embedding-only.
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
from app.retrieval.embeddings import embed

# 0.95 = "confidently the same question" — high enough to avoid serving a related
# but different question's answer; low enough to catch paraphrases. False-positive
# cache hits are worse than misses (silent wrong answers vs. extra latency).
CACHE_HIT_SIMILARITY_THRESHOLD: float = 0.95

_STATS = {"hits": 0, "misses": 0, "expired": 0}


def _collection_name(repo_id: str, commit_hash: str) -> str:
    """Namespace cache vectors by (repo_id, commit_hash) — one collection per commit."""
    safe_repo = "".join(c if c.isalnum() or c in "-_" else "_" for c in repo_id)[:40]
    safe_commit = "".join(c if c.isalnum() else "_" for c in commit_hash)[:16]
    return f"sc_{safe_repo}_{safe_commit}"


def _get_cache_collection(repo_id: str, commit_hash: str = "") -> chromadb.Collection | None:
    if not commit_hash:
        commit_hash = _get_repo_metadata(repo_id).get("commit_hash", "")
    if not commit_hash:
        commit_hash = "legacy"
    try:
        client = chromadb.PersistentClient(
            path=settings.CHROMA_DB_PATH,
            settings=chroma_settings(),
        )
    except Exception as exc:
        logger.error("semantic_cache_chroma_init_failed", error=str(exc))
        return None

    name = _collection_name(repo_id, commit_hash)
    try:
        col = client.get_collection(name)
        raw_meta = col.metadata or {}
        col_meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        if col_meta.get("embedding_model_id") != settings.EMBEDDING_MODEL:
            client.delete_collection(name)
            col = None
        elif col_meta.get("prompt_version") != PROMPT_VERSION:
            client.delete_collection(name)
            col = None
    except chromadb.errors.InvalidCollectionException:
        col = None

    if col is None:
        try:
            col = client.create_collection(
                name=name,
                metadata={
                    "embedding_model_id": settings.EMBEDDING_MODEL,
                    "prompt_version": PROMPT_VERSION,
                    "repo_id": repo_id,
                    "commit_hash": commit_hash,
                    "hnsw:space": "cosine",
                },
            )
        except Exception as exc:
            logger.error("semantic_cache_collection_create_failed", error=str(exc))
            return None
    return col


def _cosine_similarity_from_distance(distance: float) -> float:
    """Chroma cosine space: distance = 1 - cosine_similarity."""
    return 1.0 - float(distance)


# ---------------------------------------------------------------------------
# Module #24 public API
# ---------------------------------------------------------------------------

def check_cache(question: str, repo_id: str, commit_hash: str) -> dict[str, Any] | None:
    """
    Look up a verified answer for a semantically identical question.

    Returns ``{answer, sources, confidence_score}`` or ``None`` on miss.
    Uses ``embed()`` + Chroma cosine query scoped to ``(repo_id, commit_hash)``.
    """
    if not settings.SEMANTIC_CACHE_ENABLED or not commit_hash:
        return None

    try:
        query_embedding = embed(question)
    except Exception as exc:
        logger.warning("semantic_cache_embed_failed", error=str(exc))
        return None

    col = _get_cache_collection(repo_id, commit_hash)
    if col is None or col.count() == 0:
        _STATS["misses"] += 1
        return None

    try:
        results = col.query(query_embeddings=[query_embedding], n_results=1)
    except Exception as exc:
        logger.warning("semantic_cache_query_failed", error=str(exc))
        _STATS["misses"] += 1
        return None

    if not results.get("ids") or not results["ids"][0]:
        _STATS["misses"] += 1
        return None

    distances = results.get("distances")
    if not distances or not distances[0]:
        _STATS["misses"] += 1
        return None

    similarity = _cosine_similarity_from_distance(distances[0][0])
    if similarity < CACHE_HIT_SIMILARITY_THRESHOLD:
        _STATS["misses"] += 1
        return None

    meta = results["metadatas"][0][0]
    cached_at = int(meta.get("timestamp", 0))
    ttl_seconds = settings.SEMANTIC_CACHE_TTL_DAYS * 86400
    if cached_at and int(time.time()) - cached_at > ttl_seconds:
        try:
            col.delete(ids=[results["ids"][0][0]])
            _STATS["expired"] += 1
        except Exception:
            pass
        _STATS["misses"] += 1
        return None

    stored_commit = meta.get("repo_commit_hash", commit_hash)
    if stored_commit and stored_commit != commit_hash:
        _STATS["misses"] += 1
        return None

    try:
        payload = json.loads(meta["answer_json"])
    except Exception as exc:
        logger.warning("semantic_cache_deserialize_failed", error=str(exc))
        _STATS["misses"] += 1
        return None

    if payload.get("gated"):
        _STATS["misses"] += 1
        return None

    _STATS["hits"] += 1
    logger.info("semantic_cache_hit", repo_id=repo_id, commit_hash=commit_hash[:12], similarity=similarity)
    return {
        "answer": str(payload.get("answer", "")),
        "sources": payload.get("sources", []),
        "confidence_score": float(payload.get("confidence_score", 0.0)),
    }


def store(
    question: str,
    answer: dict[str, Any],
    repo_id: str,
    commit_hash: str,
    *,
    gated: bool | None = None,
) -> None:
    """
    Persist a verified answer for future INTAKE short-circuits.

    Defense in depth: rejects ``gated=True`` via explicit flag OR ``answer["gated"]``.
    Never stores error/rate-limited responses.
    """
    if not settings.SEMANTIC_CACHE_ENABLED or not commit_hash:
        return

    is_gated = bool(gated) if gated is not None else bool(answer.get("gated"))
    if is_gated:
        logger.debug("semantic_cache_store_skipped_gated", repo_id=repo_id)
        return
    if answer.get("error") or answer.get("rate_limited") or answer.get("timed_out"):
        logger.debug("semantic_cache_store_skipped_error_response", repo_id=repo_id)
        return

    try:
        query_embedding = embed(question)
    except Exception as exc:
        logger.warning("semantic_cache_embed_failed_on_store", error=str(exc))
        return

    col = _get_cache_collection(repo_id, commit_hash)
    if col is None:
        return

    payload = {
        "answer": answer.get("answer", ""),
        "sources": answer.get("sources", []),
        "confidence_score": float(answer.get("confidence_score", 0.0)),
        "gated": False,
    }

    try:
        col.add(
            ids=[f"cache_{uuid.uuid4().hex}"],
            embeddings=[query_embedding],
            metadatas=[{
                "answer_json": json.dumps(payload),
                "repo_commit_hash": commit_hash,
                "repo_id": repo_id,
                "timestamp": int(time.time()),
            }],
        )
        logger.info("semantic_cache_stored", repo_id=repo_id, commit_hash=commit_hash[:12])
    except Exception as exc:
        logger.warning("semantic_cache_store_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Legacy compatibility (answer_question_cached, tests, stats)
# ---------------------------------------------------------------------------

def answer_question(question: str, repo_id: str, **kwargs: Any) -> dict[str, Any]:
    """Patchable delegate to ``app.agent.loop.answer_question`` (tests)."""
    from app.agent.loop import answer_question as loop_answer

    return loop_answer(question, repo_id, **kwargs)


def _get_repo_metadata(repo_id: str) -> dict[str, Any]:
    from pathlib import Path

    status_file = Path(settings.REPOS_PATH) / repo_id / "sync_status.json"
    if status_file.exists():
        try:
            return json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"commit_hash": ""}


class SemanticCache:
    """Backward-compatible facade delegating to Module #24 API."""

    @staticmethod
    def get_cache_stats(repo_id: str, commit_hash: str = "") -> dict[str, Any]:
        col = _get_cache_collection(repo_id, commit_hash) if commit_hash else None
        total_entries = col.count() if col else 0
        total_requests = _STATS["hits"] + _STATS["misses"]
        hit_rate = round(_STATS["hits"] / total_requests, 2) if total_requests > 0 else 0.0
        return {
            "total_entries": total_entries,
            "hit_rate": hit_rate,
            "expired_entries": _STATS["expired"],
            "session_hits": _STATS["hits"],
            "session_misses": _STATS["misses"],
        }

    @staticmethod
    def find_nearest(
        repo_id: str,
        query_embedding: list[float],
        threshold: float | None = None,
        *,
        commit_hash: str = "",
    ) -> dict[str, Any] | None:
        _ = threshold
        if not commit_hash:
            commit_hash = _get_repo_metadata(repo_id).get("commit_hash", "")
        if not commit_hash:
            return None
        col = _get_cache_collection(repo_id, commit_hash)
        if col is None or col.count() == 0:
            return None
        try:
            results = col.query(query_embeddings=[query_embedding], n_results=1)
        except Exception:
            return None
        if not results.get("ids") or not results["ids"][0]:
            return None
        distances = results.get("distances")
        if not distances or not distances[0]:
            return None
        sim = _cosine_similarity_from_distance(distances[0][0])
        thresh = threshold if threshold is not None else CACHE_HIT_SIMILARITY_THRESHOLD
        if sim < thresh:
            return None
        meta = results["metadatas"][0][0]
        try:
            answer_dict = json.loads(meta["answer_json"])
        except Exception:
            return None
        return {
            "answer": answer_dict,
            "repo_commit_hash": meta.get("repo_commit_hash", commit_hash),
            "similarity": sim,
        }

    @staticmethod
    def store(
        repo_id: str,
        query_embedding: list[float],
        answer: dict[str, Any],
        repo_commit_hash: str,
    ) -> None:
        if answer.get("gated") or answer.get("error") or answer.get("rate_limited"):
            return
        if not settings.SEMANTIC_CACHE_ENABLED or not repo_commit_hash:
            return
        col = _get_cache_collection(repo_id, repo_commit_hash)
        if col is None:
            return
        payload = {
            "answer": answer.get("answer", ""),
            "sources": answer.get("sources", []),
            "confidence_score": float(answer.get("confidence_score", 0.0)),
            "gated": False,
        }
        try:
            col.add(
                ids=[f"cache_{uuid.uuid4().hex}"],
                embeddings=[query_embedding],
                metadatas=[{
                    "answer_json": json.dumps(payload),
                    "repo_commit_hash": repo_commit_hash,
                    "repo_id": repo_id,
                    "timestamp": int(time.time()),
                }],
            )
        except Exception as exc:
            logger.warning("semantic_cache_store_failed", error=str(exc))

    @staticmethod
    def invalidate_old_commits(repo_id: str, current_commit: str) -> None:
        _ = (repo_id, current_commit)


def _refresh_cached_answer(cached: dict[str, Any], question: str, repo_id: str) -> dict[str, Any]:
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
    return out


def answer_question_cached(question: str, repo_id: str, **kwargs) -> dict[str, Any]:
    """Legacy wrapper around ``run()`` / full pipeline with cache."""
    if not settings.SEMANTIC_CACHE_ENABLED:
        return {**answer_question(question, repo_id, **kwargs), "cache_hit": False}

    meta = _get_repo_metadata(repo_id)
    commit_hash = meta.get("commit_hash", "")

    hit = check_cache(question, repo_id, commit_hash)
    if hit:
        refreshed = _refresh_cached_answer(hit, question, repo_id)
        return {**refreshed, "cache_hit": True, "gated": False}

    result = answer_question(question, repo_id, **kwargs)
    if not result.get("gated") and not result.get("error") and not result.get("rate_limited"):
        store(question, result, repo_id, commit_hash, gated=result.get("gated"))
    return {**result, "cache_hit": False}


def sweep_expired_entries(repo_id: str, commit_hash: str = "") -> None:
    if not commit_hash:
        commit_hash = _get_repo_metadata(repo_id).get("commit_hash", "")
    col = _get_cache_collection(repo_id, commit_hash)
    if not col:
        return
    cutoff_ts = int(time.time()) - (settings.SEMANTIC_CACHE_TTL_DAYS * 86400)
    try:
        col.delete(where={"timestamp": {"$lt": cutoff_ts}})
    except Exception as exc:
        logger.error("semantic_cache_sweep_failed", error=str(exc))
