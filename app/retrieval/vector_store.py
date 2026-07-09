# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/retrieval/vector_store.py
-----------------------------
ChromaDB integration for storing and querying chunk embeddings.

Responsibility boundary
-----------------------
This module manages the local ChromaDB persistent client, the collection lifecycle,
and the safety mechanism that prevents mixing embeddings from different models.
It does NOT:
  - compute embeddings (see `embeddings.py`),
  - manage BM25 indexes (see `bm25_store.py`),
  - perform RRF hybrid fusion (see `hybrid_search.py`).

Embedding-model lock
--------------------
A collection's metadata stores `embedding_model_id` upon creation.
If a later ingest tries to reuse this collection while `settings.EMBEDDING_MODEL`
has changed, this module rejects the ingest with `ModelMismatchError`.
Silently mixing embeddings from different model spaces produces garbage cosine
similarities.  The caller must pass `force_reindex=True` to wipe and rebuild.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    import chromadb

from app.chroma_client import persistent_client
from app.config import settings
from app.observability.logging_config import logger
from app.parsing.chunker import CodeChunk
from app.retrieval.embeddings import embed, embed_batch

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ModelMismatchError(RuntimeError):
    """
    Raised when attempting to insert chunks into a collection created with
    a different embedding model.
    """


# ---------------------------------------------------------------------------
# Singleton Client
# ---------------------------------------------------------------------------
_CHROMA_CLIENT: "chromadb.ClientAPI | None" = None

def _get_client() -> "chromadb.ClientAPI":
    """Return the singleton ChromaDB PersistentClient."""
    global _CHROMA_CLIENT
    import chromadb

    if _CHROMA_CLIENT is None:
        if settings.CHROMA_HOST:
            logger.info("connecting_to_remote_chroma", host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
            _CHROMA_CLIENT = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        else:
            db_path = Path(settings.CHROMA_DB_PATH)
            db_path.mkdir(parents=True, exist_ok=True)
            _CHROMA_CLIENT = persistent_client(db_path)
    return _CHROMA_CLIENT


# ---------------------------------------------------------------------------
# Collection Management
# ---------------------------------------------------------------------------

def _collection_name_for(repo_id: str) -> str:
    """
    Return the Chroma collection name for a given repo.
    Collection names must match ^[a-zA-Z0-9_-]{3,63}$
    repo_id is a sha256 hex string, which is perfectly safe.
    """
    return f"{repo_id[:50]}_chunks"


def get_collection(repo_id: str) -> chromadb.Collection | None:
    """
    Return the collection for *repo_id*, or None if it doesn't exist.
    """
    client = _get_client()
    name = _collection_name_for(repo_id)
    try:
        return client.get_collection(name)
    except Exception as exc:
        # Chroma raises ValueError or InvalidCollectionException when missing;
        # version mismatches between HttpClient and server also surface here.
        logger.debug("get_collection_failed", collection_name=name, error=str(exc))
        return None


def get_collection_by_name(
    client: "chromadb.ClientAPI",
    collection_name: str,
) -> chromadb.Collection | None:
    """Return a collection by name, or None if it does not exist."""
    try:
        return client.get_collection(collection_name)
    except Exception as exc:
        logger.debug(
            "get_collection_by_name_failed",
            collection_name=collection_name,
            error=str(exc),
        )
        return None


# ---------------------------------------------------------------------------
# Public API — Ingestion
# ---------------------------------------------------------------------------

def store_chunks(
    repo_id: str,
    chunks: list[CodeChunk],
    force_reindex: bool = False,
) -> None:
    """
    Embed and store *chunks* in ChromaDB for *repo_id*.

    Parameters
    ----------
    repo_id:
        The repository identifier from Module 3.
    chunks:
        The chunks produced by Module 5.
    force_reindex:
        If True, entirely wipes the existing collection and rebuilds it.
        This is the recovery path for a ModelMismatchError.

    Raises
    ------
    ModelMismatchError
        If the collection exists but was created with a different embedding
        model than `settings.EMBEDDING_MODEL`, and force_reindex is False.
    """
    log = logger.bind(repo_id=repo_id)
    client = _get_client()
    collection_name = _collection_name_for(repo_id)
    current_model = settings.EMBEDDING_MODEL

    if force_reindex:
        try:
            client.delete_collection(collection_name)
            log.info("collection_wiped_for_reindex", collection_name=collection_name)
        except Exception:
            pass  # Ignored if it didn't exist

    collection = get_collection_by_name(client, collection_name)

    if collection is None:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"embedding_model_id": current_model},
        )
        log.info("collection_created", collection_name=collection_name, model=current_model)
    else:
        # Check model lock
        stored_model = collection.metadata.get("embedding_model_id")
        if stored_model and stored_model != current_model:
            raise ModelMismatchError(
                f"Collection {collection_name} was created with '{stored_model}', "
                f"but current system model is '{current_model}'. "
                "Pass force_reindex=True to wipe and rebuild."
            )

    if not chunks:
        log.warning("no_chunks_to_store")
        return

    # Prepare batch insertion payloads
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk in chunks:
        # Unique ID combining normalized path and function name to prevent clashes
        chunk_id = f"chunk_{chunk.fingerprint}"
        ids.append(chunk_id)
        documents.append(chunk.chunk_text)
        metadatas.append({
            "file_path": chunk.file_path,
            "display_path": chunk.display_path,
            "function_name": chunk.function_name,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "type": chunk.type,
            "language": chunk.language,
            "fingerprint": chunk.fingerprint,
            "embedding_model_id": current_model,
        })

    # Embed in batch for efficiency
    log.info("computing_embeddings", n_chunks=len(documents))
    embeddings = embed_batch(documents)

    # Upsert (insert or update)
    log.info("upserting_to_chroma")
    # Chroma handles batching internally if the payload is huge, but usually
    # upserting thousands of items at once is fine.
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )
    log.info("store_chunks_completed", n_stored=len(ids))


# ---------------------------------------------------------------------------
# Public API — Retrieval
# ---------------------------------------------------------------------------

@dataclass
class VectorSearchResult:
    """A single hit from the vector store."""
    id: str
    score: float             # raw distance/similarity (depends on chroma metric, default is l2, but we treat it loosely before RRF)
    document: str
    metadata: dict[str, Any]


def search_vectors(
    repo_id: str,
    query: str,
    n_results: int = 20,
) -> list[VectorSearchResult]:
    """
    Search the vector store for *query* and return the top *n_results*.

    Returns an empty list if the collection does not exist.
    """
    collection = get_collection(repo_id)
    if collection is None:
        return []

    query_embedding = embed(query)

    # Clamp n_results to avoid HNSW "Cannot return the results in a contigious 2D array" error on small repos
    actual_n_results = min(n_results, collection.count())
    if actual_n_results == 0:
        return []

    # Query Chroma
    # Default metric is L2 distance, so lower distance = better match.
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_n_results,
        include=["documents", "metadatas", "distances"],
    )

    if not results or not results["ids"] or not results["ids"][0]:
        return []

    # Flatten the results (Chroma returns lists of lists because it supports multi-query)
    out: list[VectorSearchResult] = []
    ids = results["ids"][0]
    distances = results["distances"][0] if results["distances"] else [0.0]*len(ids)
    docs = results["documents"][0] if results["documents"] else [""]*len(ids)
    metas = results["metadatas"][0] if results["metadatas"] else [{}]*len(ids)

    for i, _id in enumerate(ids):
        out.append(VectorSearchResult(
            id=_id,
            # We negate the L2 distance so that higher is better, making it
            # semantically compatible with min-max normalization where 1 is best.
            score=-float(distances[i]),
            document=str(docs[i]),
            metadata=metas[i],
        ))

    return out
