# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/retrieval/embeddings.py
---------------------------
Core embedding utility for the codenavigator.

Responsibility boundary
-----------------------
This module loads the embedding model specified by `settings.EMBEDDING_MODEL`
and provides clean, stateless functions to embed text strings.
It does NOT:
  - talk to ChromaDB (see `vector_store.py`),
  - execute BM25 searches (see `bm25_store.py`),
  - implement reranking (Module 6b).

Reusability
-----------
This file exposes the exact `embed()` and `embed_batch()` functions used by
the semantic cache (Module 10) and agent tools (Module 9). It must remain a
standalone utility, free of vector-store or BM25 dependencies.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Sequence

from app.config import settings
from app.observability.logging_config import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Global model instance
# Loaded lazily on first use to avoid blocking app startup or tests that don't embed.
# ---------------------------------------------------------------------------
_MODEL: SentenceTransformer | None = None


def _get_model() -> "SentenceTransformer":
    """Return the global SentenceTransformer, initializing it if necessary."""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        model_name = settings.EMBEDDING_MODEL
        logger.info("loading_embedding_model", model_name=model_name)
        # Device is auto-selected by sentence-transformers (CUDA/MPS/CPU).
        # We don't hardcode it so it runs optimally on the deployment host.
        try:
            _MODEL = SentenceTransformer(model_name)
            logger.info("embedding_model_loaded", model_name=model_name)
        except Exception as exc:
            logger.error("embedding_model_load_failed", model_name=model_name, error=str(exc))
            raise RuntimeError(f"Failed to load embedding model: {exc}") from exc
    return _MODEL


def get_model() -> SentenceTransformer:
    """Return the global SentenceTransformer, initializing it if necessary."""
    return _get_model()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

import hashlib
import shelve
from pathlib import Path
from typing import Any

def _get_cache_path() -> Path:
    cache_dir = Path(settings.CHROMA_DB_PATH).parent / "embedding_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cache.db"

def embed(text: str) -> list[float]:
    """Return the embedding vector for a text string using the SentenceTransformer model."""
    return embed_batch([text])[0]


def embed_batch(texts: Sequence[str]) -> list[list[float]]:
    """Return a list of embedding vectors for a sequence of strings using the SentenceTransformer model."""
    cache_path = str(_get_cache_path())
    
    # Pre-compute hashes
    text_hashes = [hashlib.md5(t.encode('utf-8')).hexdigest() for t in texts]
    results = [None] * len(texts)
    uncached_indices = []
    uncached_texts = []
    
    with shelve.open(cache_path) as cache:
        for i, (t_hash, text) in enumerate(zip(text_hashes, texts)):
            if t_hash in cache:
                results[i] = cache[t_hash]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
                
        if uncached_texts:
            model = _get_model()
            new_embeddings = model.encode(list(uncached_texts), normalize_embeddings=True).tolist()
            for idx, emb, t_hash in zip(uncached_indices, new_embeddings, [text_hashes[i] for i in uncached_indices]):
                results[idx] = emb
                cache[t_hash] = emb
                
    return results


def embed_chunks(chunks: list[Any]) -> list[Any]:
    """
    Generate normalized embeddings for a list of Chunk objects and attach them
    under the .vector attribute.
    """
    valid_chunks = []
    valid_texts = []
    for chunk in chunks:
        txt = getattr(chunk, "text", getattr(chunk, "chunk_text", ""))
        if not txt or not txt.strip():
            logger.warning("empty_chunk_text_skipped", chunk_id=getattr(chunk, "fingerprint", "unknown"))
            continue
        valid_chunks.append(chunk)
        valid_texts.append(txt)

    if valid_texts:
        vectors = embed_batch(valid_texts)
        for chunk, vector in zip(valid_chunks, vectors):
            chunk.vector = vector

    return chunks


def embed_query(text: str) -> list[float]:
    """
    Generate a normalized embedding vector for a raw query string.
    """
    if not text or not text.strip():
        raise ValueError("Query text cannot be empty or whitespace")
    return embed(text)

