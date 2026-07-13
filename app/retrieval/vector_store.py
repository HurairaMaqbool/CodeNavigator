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

from pathlib import Path
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    import chromadb

from app.chroma_client import persistent_client
from app.config import settings
from app.observability.logging_config import logger
from app.parsing.chunker import CodeChunk
from app.retrieval.embeddings import embed

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
        delete_repo(repo_id)

    collection = get_collection_by_name(client, collection_name)
    if collection is not None:
        # Check model lock
        stored_model = collection.metadata.get("embedding_model_id")
        if stored_model and stored_model != current_model:
            raise ModelMismatchError(
                f"Collection {collection_name} was created with '{stored_model}', "
                f"but current system model is '{current_model}'. "
                "Pass force_reindex=True to wipe and rebuild."
            )

    from app.retrieval.embeddings import embed_chunks
    embed_chunks(chunks)
    upsert_chunks(repo_id, chunks)


def upsert_chunks(repo_id: str, chunks: list[Any]) -> None:
    """
    Replace all vectors for *repo_id* with the provided pre-embedded chunks.

    Uses per-repo Chroma collections for storage-layer isolation. Re-ingestion
    deletes the prior collection before insert so stale chunk vectors never
    accumulate across versions.
    """
    log = logger.bind(repo_id=repo_id)
    client = _get_client()
    collection_name = _collection_name_for(repo_id)
    current_model = settings.EMBEDDING_MODEL

    if not chunks:
        log.warning("no_chunks_to_upsert")
        return

    # Replace-semantics per repo_id: wipe then rebuild (never duplicate stale IDs).
    delete_repo(repo_id)
    collection = client.create_collection(
        name=collection_name,
        metadata={"embedding_model_id": current_model, "repo_id": repo_id},
    )

    ids: list[str] = []
    embeddings: list[list[float]] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk in chunks:
        vector = getattr(chunk, "vector", None)
        if vector is None:
            logger.warning(
                "chunk_missing_vector_attribute",
                chunk_id=getattr(chunk, "fingerprint", "unknown"),
            )
            continue

        chunk_id = f"chunk_{chunk.fingerprint}"
        ids.append(chunk_id)
        embeddings.append(vector)
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
            "repo_id": repo_id,
        })

    if ids:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        log.info("upsert_chunks_completed", n_stored=len(ids))

    from app.ingestion.metadata_store import metadata_store, Stage
    try:
        metadata_store.update(repo_id, Stage.INDEXING, progress="Indexed chunks in vector store")
    except Exception as exc:
        logger.warning("failed_to_write_indexing_progress_checkpoint", error=str(exc))


def delete_repo(repo_id: str) -> None:
    """
    Wipe the collection for repo_id from the vector store.
    """
    client = _get_client()
    collection_name = _collection_name_for(repo_id)
    try:
        client.delete_collection(collection_name)
        logger.info("collection_deleted", collection_name=collection_name)
    except Exception as exc:
        logger.debug("delete_collection_skipped", collection_name=collection_name, error=str(exc))


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


def query(
    repo_id: str,
    query_vector: list[float],
    top_k: int = 20,
) -> list[dict[str, Any]]:
    """
    Search the vector store for nearest neighbors of query_vector inside repo_id.

    Forward Interface Contract:
    --------------------------
    Returns a list of dicts:
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
    Where score is the similarity score (cosine similarity or normalized distance).
    """
    collection = get_collection(repo_id)
    if collection is None:
        return []

    actual_top_k = min(top_k, collection.count())
    if actual_top_k == 0:
        return []

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=actual_top_k,
        include=["documents", "metadatas", "distances"],
    )

    if not results or not results["ids"] or not results["ids"][0]:
        return []

    out = []
    ids = results["ids"][0]
    distances = results["distances"][0] if results["distances"] else [2.0] * len(ids)
    metas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)

    for i in range(len(ids)):
        # Calculate cosine similarity from L2 distance
        l2_sq = float(distances[i])
        cosine_sim = 1.0 - (l2_sq / 2.0)
        cosine_sim = max(0.0, min(1.0, cosine_sim))

        out.append({
            "chunk": results["documents"][0][i] if (results.get("documents") and results["documents"][0]) else "",
            "chunk_metadata": metas[i],
            "score": cosine_sim,
        })

    return out


def search_vectors(
    repo_id: str,
    query_str: str,
    n_results: int = 20,
) -> list[VectorSearchResult]:
    """
    Search the vector store for *query_str* and return the top *n_results*.

    Returns an empty list if the collection does not exist.
    """
    collection = get_collection(repo_id)
    if collection is None:
        return []

    query_embedding = embed(query_str)

    actual_n_results = min(n_results, collection.count())
    if actual_n_results == 0:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_n_results,
        include=["documents", "metadatas", "distances"],
    )

    if not results or not results["ids"] or not results["ids"][0]:
        return []

    out: list[VectorSearchResult] = []
    ids = results["ids"][0]
    distances = results["distances"][0] if results["distances"] else [0.0]*len(ids)
    docs = results["documents"][0] if results["documents"] else [""]*len(ids)
    metas = results["metadatas"][0] if results["metadatas"] else [{}]*len(ids)

    for i, _id in enumerate(ids):
        out.append(VectorSearchResult(
            id=_id,
            score=-float(distances[i]),
            document=str(docs[i]),
            metadata=metas[i],
        ))

    return out
