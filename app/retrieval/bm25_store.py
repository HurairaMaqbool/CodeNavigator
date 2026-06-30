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

import os
import pickle
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import]

from app.config import settings
from app.observability.logging_config import logger
from app.parsing.chunker import CodeChunk

# ---------------------------------------------------------------------------
# Simple tokenizer
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """
    Fast, simple tokenizer for code BM25.
    Lowercases, strips punctuation boundaries, keeps alphanumeric segments.
    """
    # Find all contiguous alphanumeric+underscore sequences
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


# ---------------------------------------------------------------------------
# Storage / persistence
# ---------------------------------------------------------------------------

def _index_path_for(repo_id: str) -> Path:
    """Return the absolute path to the BM25 pickle for *repo_id*."""
    return Path(settings.BM25_INDEX_PATH) / repo_id / "bm25.pkl"

_BM25_CACHE: dict[str, tuple[BM25Okapi, list[dict[str, Any]]]] = {}


# ---------------------------------------------------------------------------
# Public API — Ingestion
# ---------------------------------------------------------------------------

def build_bm25_index(
    repo_id: str,
    chunks: list[CodeChunk],
) -> None:
    """
    Build and persist a BM25 index over *chunks*, always overwriting.
    """
    log = logger.bind(repo_id=repo_id)
    pkl_path = _index_path_for(repo_id)

    if not chunks:
        log.warning("no_chunks_for_bm25")
        if pkl_path.exists():
            pkl_path.unlink()
        _BM25_CACHE.pop(repo_id, None)
        return

    # Extract texts and IDs in parallel
    corpus_tokens: list[list[str]] = []
    chunk_ids: list[str] = []
    records: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk_id = f"chunk_{chunk.fingerprint}"
        chunk_ids.append(chunk_id)
        # Tokenize the EXACT same text that goes into the vector store
        corpus_tokens.append(_tokenize(chunk.chunk_text))
        records.append({
            "id": chunk_id,
            "document": chunk.chunk_text,
            "metadata": {
                "file_path": chunk.file_path,
                "display_path": chunk.display_path,
                "function_name": chunk.function_name,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "type": chunk.type,
                "language": chunk.language,
                "fingerprint": chunk.fingerprint,
            }
        })

    log.info("building_bm25_index", n_chunks=len(chunk_ids))
    bm25 = BM25Okapi(corpus_tokens)

    # Persist as a tuple: (BM25Okapi, list of records aligned with the index)
    pkl_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = (bm25, records)
    with pkl_path.open("wb") as f:
        pickle.dump(data, f)
        
    _BM25_CACHE[repo_id] = data
    
    log.info("bm25_index_built", path=str(pkl_path))


def load_bm25_index(repo_id: str) -> tuple[BM25Okapi, list[dict[str, Any]]] | None:
    """
    Load the BM25 index and records from disk if it exists, caching it in memory.
    """
    if repo_id in _BM25_CACHE:
        return _BM25_CACHE[repo_id]
        
    pkl_path = _index_path_for(repo_id)
    if not pkl_path.exists():
        return None
        
    with pkl_path.open("rb") as f:
        data = pickle.load(f)
        _BM25_CACHE[repo_id] = data
        return data


def store_bm25(
    repo_id: str,
    chunks: list[CodeChunk],
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

    build_bm25_index(repo_id, chunks)


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


def search_bm25(
    repo_id: str,
    query: str,
    top_n: int = 20,
) -> list[BM25SearchResult]:
    """
    Search the BM25 index for *query* and return the top *top_n*.

    Returns an empty list if the index does not exist.
    """
    start_time = time.perf_counter()
    
    loaded = load_bm25_index(repo_id)
    if not loaded:
        return []
    bm25, records = loaded

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)
    
    # Get top_n indices sorted by descending score
    # score == 0.0 means no matching tokens at all, we filter those out.
    top_indices = sorted(
        [i for i, s in enumerate(scores) if s > 0.0],
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
