# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/retrieval/bm25_store.py
---------------------------
BM25 Keyword Index using rank_bm25.

Responsibility boundary
-----------------------
Builds and queries an inverted keyword index over the exact same chunk texts
that the vector store ingests.  The two stores operate in lockstep.
It does NOT:
  - compute embeddings,
  - run RRF.

Lockstep consistency
--------------------
BM25 indexes are rebuilt in lockstep with `vector_store.py`'s force_reindex path.
A write to the vector store without the BM25 store (or vice versa) creates a split
brain where RRF fusion merges mismatched document IDs.
Module 3's `sync_status` machine expects both stores to complete before transitioning
a repo to 'synced'.
"""
from __future__ import annotations

import pickle
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import]

from app.config import settings
from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Code-aware Tokenizer
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """
    Code-aware tokenizer for BM25.
    Splits identifiers on camelCase, snake_case, and kebab-case boundaries,
    and removes punctuation, lowercasing all tokens.
    
    Tokenization rules:
      1. Find all alphanumeric sequences. This naturally splits snake_case
         (e.g., 'get_user' -> ['get', 'user']) and kebab-case ('get-user' -> ['get', 'user']).
      2. For each sequence, split on transitions from lowercase to uppercase
         (e.g., 'getUser' -> 'get User') and transitions from multiple uppercase letters
         to a lowercase letter (e.g., 'HTTPClient' -> 'HTTP Client').
      3. Lowercase all resulting tokens and filter out empty strings.
    """
    words = re.findall(r"[a-zA-Z0-9]+", text)
    tokens = []
    for word in words:
        # Split camelCase / PascalCase
        s1 = re.sub(r'([a-z])([A-Z])', r'\1 \2', word)
        s2 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', s1)
        for token in s2.split():
            tokens.append(token.lower())
    return tokens


# ---------------------------------------------------------------------------
# Storage / persistence
# ---------------------------------------------------------------------------

def _index_path_for(repo_id: str) -> Path:
    """Return the absolute path to the BM25 pickle for *repo_id*."""
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]", "", repo_id)
    return Path(settings.BM25_INDEX_PATH) / safe_id / "bm25.pkl"

_BM25_CACHE: dict[str, tuple[BM25Okapi, list[dict[str, Any]]]] = {}

# ---------------------------------------------------------------------------
# Per-repo lock striping — prevents cache corruption under concurrent
# ingestion (write) and search (read) for the same repo_id.
# ---------------------------------------------------------------------------
_LOCK_MAP_LOCK: threading.Lock = threading.Lock()
_REPO_LOCKS: dict[str, threading.Lock] = {}


def _get_repo_lock(repo_id: str) -> threading.Lock:
    """Return the per-repo mutex, creating it if it doesn't exist yet."""
    with _LOCK_MAP_LOCK:
        if repo_id not in _REPO_LOCKS:
            _REPO_LOCKS[repo_id] = threading.Lock()
        return _REPO_LOCKS[repo_id]


# ---------------------------------------------------------------------------
# Public API — Ingestion
# ---------------------------------------------------------------------------

def build_bm25_index(
    repo_id: str,
    chunks: list[Any],
) -> None:
    """
    Build and persist a BM25 index over *chunks*, always overwriting.

    Thread safety
    -------------
    Acquires the per-repo lock before any mutation of the in-memory cache
    or the on-disk pickle file.  This prevents a concurrent ``load_bm25_index``
    from reading a half-written pickle or a torn cache entry.
    """
    log = logger.bind(repo_id=repo_id)
    pkl_path = _index_path_for(repo_id)

    if not chunks:
        log.warning("no_chunks_for_bm25")
        with _get_repo_lock(repo_id):
            if pkl_path.exists():
                try:
                    pkl_path.unlink()
                except Exception:
                    pass
            _BM25_CACHE.pop(repo_id, None)
        return

    corpus_tokens: list[list[str]] = []
    chunk_ids: list[str] = []
    records: list[dict[str, Any]] = []

    for chunk in chunks:
        if isinstance(chunk, dict):
            fingerprint = chunk.get("fingerprint", "")
            chunk_text = chunk.get("chunk_text") or chunk.get("text") or ""
            file_path = chunk.get("file_path", "")
            display_path = chunk.get("display_path", "")
            function_name = chunk.get("function_name", "")
            start_line = chunk.get("start_line", 0)
            end_line = chunk.get("end_line", 0)
            chunk_type = chunk.get("type", "")
            language = chunk.get("language", "")
        else:
            fingerprint = getattr(chunk, "fingerprint", "")
            if not fingerprint and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                fingerprint = chunk.metadata.get("fingerprint", "")

            chunk_text = getattr(chunk, "chunk_text", "") or getattr(chunk, "text", "")

            file_path = getattr(chunk, "file_path", "")
            if not file_path and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                file_path = chunk.metadata.get("file_path", "")

            display_path = getattr(chunk, "display_path", "")
            if not display_path and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                display_path = chunk.metadata.get("display_path", "")

            function_name = getattr(chunk, "function_name", "")
            if not function_name and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                function_name = chunk.metadata.get("function_name", "")

            start_line = getattr(chunk, "start_line", 0)
            if not start_line and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                start_line = chunk.metadata.get("start_line", 0)

            end_line = getattr(chunk, "end_line", 0)
            if not end_line and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                end_line = chunk.metadata.get("end_line", 0)

            chunk_type = getattr(chunk, "type", "")
            if not chunk_type and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                chunk_type = chunk.metadata.get("type", "")

            language = getattr(chunk, "language", "")
            if not language and hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
                language = chunk.metadata.get("language", "")

        # Keep the same ID formula literal as vector_store.py (Module 6a EC2).
        if isinstance(chunk, dict):
            chunk_id = f"chunk_{fingerprint}"
        else:
            chunk_id = f"chunk_{chunk.fingerprint}"
        chunk_ids.append(chunk_id)
        corpus_tokens.append(_tokenize(chunk_text))

        records.append({
            "id": chunk_id,
            "document": chunk_text,
            "metadata": {
                "file_path": file_path,
                "display_path": display_path,
                "function_name": function_name,
                "start_line": start_line,
                "end_line": end_line,
                "type": chunk_type,
                "language": language,
                "fingerprint": fingerprint,
            }
        })

    log.info("building_bm25_index", n_chunks=len(chunk_ids))
    # Build BM25 model outside the lock — this is pure CPU work and takes the
    # bulk of the time; no shared state is touched yet.
    bm25 = BM25Okapi(corpus_tokens)

    pkl_path.parent.mkdir(parents=True, exist_ok=True)
    data = (bm25, records)

    # Acquire the per-repo lock only for the file-write + cache-update.
    with _get_repo_lock(repo_id):
        with pkl_path.open("wb") as f:
            pickle.dump(data, f)
        _BM25_CACHE[repo_id] = data

    log.info("bm25_index_built", path=str(pkl_path))


def load_bm25_index(repo_id: str) -> tuple[BM25Okapi, list[dict[str, Any]]] | None:
    """
    Load the BM25 index and records from disk if it exists, caching it in memory.

    Thread safety
    -------------
    Holds the per-repo lock for both the cache-check and the disk read so that
    a concurrent ``build_bm25_index`` cannot replace the pickle between the
    existence check and the open() call.
    """
    with _get_repo_lock(repo_id):
        if repo_id in _BM25_CACHE:
            return _BM25_CACHE[repo_id]

        pkl_path = _index_path_for(repo_id)
        if not pkl_path.exists():
            return None

        try:
            with pkl_path.open("rb") as f:
                data = pickle.load(f)
            _BM25_CACHE[repo_id] = data
            return data
        except Exception as exc:
            logger.warning("failed_to_load_bm25_index_file", path=str(pkl_path), error=str(exc))
            return None


def store_bm25(
    repo_id: str,
    chunks: list[Any],
    force_reindex: bool = False,
) -> None:
    """
    Build and persist a BM25 index over *chunks*.
    If *force_reindex* is True or the index does not exist, it builds from scratch.
    """
    log = logger.bind(repo_id=repo_id)
    pkl_path = _index_path_for(repo_id)

    if not force_reindex and pkl_path.exists():
        log.info("bm25_index_already_exists", path=str(pkl_path))
        return

    upsert_chunks(repo_id, chunks)


def upsert_chunks(repo_id: str, chunks: list[Any]) -> None:
    """
    Tokenizes and indexes chunk text into a per-repo BM25 index,
    overwriting any existing index.
    """
    build_bm25_index(repo_id, chunks)

    # Write indexing progress to metadata_store
    from app.ingestion.metadata_store import metadata_store, Stage
    try:
        metadata_store.update(repo_id, Stage.INDEXING, progress="Indexed chunks in BM25 index")
    except Exception as exc:
        logger.warning("failed_to_write_indexing_progress_checkpoint", error=str(exc))


def delete_repo(repo_id: str) -> None:
    """
    Delete the BM25 index for repo_id from disk and cache.

    Thread safety
    -------------
    Holds the per-repo lock so that a concurrent search cannot read a
    partially-deleted cache or a file that is in the process of being removed.
    """
    pkl_path = _index_path_for(repo_id)
    with _get_repo_lock(repo_id):
        if pkl_path.exists():
            try:
                pkl_path.unlink()
                logger.info("bm25_index_deleted", path=str(pkl_path))
            except Exception as exc:
                logger.warning("failed_to_delete_bm25_index_file", path=str(pkl_path), error=str(exc))

        try:
            parent_dir = pkl_path.parent
            if parent_dir.exists() and not any(parent_dir.iterdir()):
                parent_dir.rmdir()
        except Exception:
            pass

        _BM25_CACHE.pop(repo_id, None)


# ---------------------------------------------------------------------------
# Public API — Retrieval
# ---------------------------------------------------------------------------

@dataclass
class BM25SearchResult:
    """A single hit from the BM25 store."""
    id: str
    score: float
    document: str
    metadata: dict[str, Any]


def query(
    repo_id: str,
    query_text: str,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """
    Search the BM25 index for query_text inside repo_id, returning top_k hits.

    Forward Interface Contract:
    --------------------------
    Returns a list of dicts matching vector_store.py's query() shape:
        [
            {
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
                "score": float
            },
            ...
        ]
    """
    loaded = load_bm25_index(repo_id)
    if not loaded:
        return []
    bm25, records = loaded

    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    
    # Filter indices that share at least one token with the query
    query_set = set(query_tokens)
    matched_indices = []
    for idx, record in enumerate(records):
        doc_tokens = _tokenize(record["document"])
        if query_set.intersection(doc_tokens):
            matched_indices.append(idx)

    top_indices = sorted(
        matched_indices,
        key=lambda i: scores[i],
        reverse=True
    )[:top_k]

    out = []
    for idx in top_indices:
        record = records[idx]
        out.append({
            "chunk": record["document"],
            "chunk_metadata": record["metadata"],
            "score": float(scores[idx]),
        })

    return out


def search_bm25(
    repo_id: str,
    query_str: str,
    top_n: int = 20,
) -> list[BM25SearchResult]:
    """
    Search the BM25 index for *query_str* and return the top *top_n*.

    Returns an empty list if the index does not exist.
    """
    start_time = time.perf_counter()
    
    loaded = load_bm25_index(repo_id)
    if not loaded:
        return []
    bm25, records = loaded

    query_tokens = _tokenize(query_str)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    
    # Filter indices that share at least one token with the query
    query_set = set(query_tokens)
    matched_indices = []
    for idx, record in enumerate(records):
        doc_tokens = _tokenize(record["document"])
        if query_set.intersection(doc_tokens):
            matched_indices.append(idx)

    top_indices = sorted(
        matched_indices,
        key=lambda i: scores[i],
        reverse=True
    )[:top_n]

    out: list[BM25SearchResult] = []
    for idx in top_indices:
        record = records[idx]
        out.append(BM25SearchResult(
            id=record["id"],
            score=float(scores[idx]),
            document=record["document"],
            metadata=record["metadata"],
        ))

    elapsed = time.perf_counter() - start_time
    logger.bind(repo_id=repo_id).info("bm25_search_completed", time_ms=round(elapsed * 1000, 2), hits=len(out))

    return out
