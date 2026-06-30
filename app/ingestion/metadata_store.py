"""
app/ingestion/metadata_store.py
--------------------------------
Persistent per-repo lifecycle tracking.

State machine
-------------
Every ingested repository passes through exactly three states:

    pending ──────► synced
       │
       └──────────► failed

Transitions
~~~~~~~~~~~
- ``pending``  Set the instant the ingestion lock is acquired, *before* any
               vector or graph store is touched.  This is the "dirty" marker —
               if the process crashes, the record stays ``pending`` until the
               TTL expires (Module 3 / locking.py handles that).

- ``synced``   Set only after *both* the vector store (Module 6) and the graph
               store (Module 7) confirm a successful write.  This module
               exposes the :meth:`~MetadataStore.mark_synced` hook; Modules 6
               and 7 call it once they both report success.

- ``failed``   Set on any unrecoverable error during ingestion, with the error
               reason recorded.

Schema versioning
-----------------
``SCHEMA_VERSION = 1`` is stamped on every record.  When parsing / chunking
format changes in a future module, increment this constant here.  Downstream
modules (e.g. Module 6 — vector store) can compare the stored schema_version
against the current one and flag stale indexes rather than silently misreading
them.

  Future authors: bump SCHEMA_VERSION in *this* file only; it is the single
  source of truth for the index format version.

Storage layout
--------------
One JSON file per repository::

    {REPOS_PATH}/{repo_id}/metadata.json

Thread safety
~~~~~~~~~~~~~
A per-repo ``threading.Lock`` guards reads and writes so concurrent async
requests for the same repo see a consistent view of the metadata.

Public API (used by Module 9 / agent and Module 12 / API layer)
---------------------------------------------------------------
    from app.ingestion.metadata_store import metadata_store, RepoMetadata

    meta: RepoMetadata | None = metadata_store.get(repo_id)
    if meta is None or meta.sync_status != "synced":
        raise ...  # refuse to serve /chat until fully indexed

    metadata_store.mark_pending(repo_id, repo_url, ref)
    metadata_store.mark_synced(repo_id, commit_hash=..., cloned_at=...)
    metadata_store.mark_failed(repo_id, error_reason="...")
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.config import settings
from app.observability.logging_config import logger


# ---------------------------------------------------------------------------
# Schema version — bump this whenever parsing/chunking/embedding format changes
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 1
"""
Increment this constant whenever the index format changes (e.g. new chunking
strategy, embedding model swap, graph schema change).  Every new metadata
record is stamped with the current value.  Future modules compare it to detect
stale indexes that need re-ingestion.
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

SyncStatus = Literal["pending", "synced", "failed"]


@dataclass
class RepoMetadata:
    """
    Snapshot of a repository's ingestion lifecycle.

    All datetime fields are stored as ISO-8601 strings with UTC timezone so
    they serialise cleanly to/from JSON and compare correctly across processes.
    """
    repo_id: str
    repo_url: str
    ref: str                         # resolved branch / tag
    sync_status: SyncStatus          # pending | synced | failed
    schema_version: int              # always SCHEMA_VERSION at write time

    # Set once the clone completes
    commit_hash: str | None = None
    cloned_at: str | None = None     # ISO-8601 UTC

    # Set the moment the lock is acquired (pending transition)
    sync_started_at: str | None = None  # ISO-8601 UTC

    # Set on failed transition
    error_reason: str | None = None

    # Multi-tenant isolation (Phase 2)
    org_id: str = "default"


# ---------------------------------------------------------------------------
# Metadata store
# ---------------------------------------------------------------------------

class MetadataStore:
    """
    JSON-backed, thread-safe metadata store.

    All public methods acquire a per-repo lock before reading or writing the
    backing JSON file.  This makes concurrent async requests for the same
    repo_id see a consistent state without using any external database.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir: Path | None = base_dir  # override for tests
        self._registry_lock = threading.Lock()
        self._repo_locks: dict[str, threading.Lock] = {}

    def _root(self) -> Path:
        return self._base_dir if self._base_dir is not None else Path(settings.REPOS_PATH)

    def _metadata_path(self, repo_id: str) -> Path:
        return self._root() / repo_id / "metadata.json"

    def _alias_path(self, job_id: str) -> Path:
        return self._root() / job_id / "alias.json"


    def _get_repo_lock(self, repo_id: str) -> threading.Lock:
        with self._registry_lock:
            if repo_id not in self._repo_locks:
                self._repo_locks[repo_id] = threading.Lock()
            return self._repo_locks[repo_id]

    def _read_raw(self, repo_id: str) -> dict | None:
        """Read the raw JSON dict from disk, or None if the file doesn't exist."""
        path = self._metadata_path(repo_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("metadata_read_error", repo_id=repo_id, error=str(exc))
            return None

    def _write_raw(self, repo_id: str, data: dict) -> None:
        """Atomically write *data* to disk."""
        path = self._metadata_path(repo_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file first, then rename — avoids partial writes.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _dict_to_meta(self, d: dict) -> RepoMetadata:
        """Convert a raw dict (from JSON) to a :class:`RepoMetadata`."""
        return RepoMetadata(
            repo_id=d["repo_id"],
            repo_url=d["repo_url"],
            ref=d["ref"],
            sync_status=d["sync_status"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            commit_hash=d.get("commit_hash"),
            cloned_at=d.get("cloned_at"),
            sync_started_at=d.get("sync_started_at"),
            error_reason=d.get("error_reason"),
            org_id=d.get("org_id", "default"),
        )

    # ── Public read API ───────────────────────────────────────────────────────

    def get(self, repo_id: str) -> RepoMetadata | None:
        """
        Return the metadata for *repo_id*, or ``None`` if it has never been
        ingested.

        Module 9 (agent loop) and Module 12 (API layer) call this before
        serving ``/chat`` or ``/diagram`` requests to verify the repo is
        ``synced``.
        """
        lock = self._get_repo_lock(repo_id)
        with lock:
            raw = self._read_raw(repo_id)
            if raw:
                logger.debug("metadata_retrieved", repo_id=repo_id, sync_status=raw.get("sync_status"))
            else:
                logger.debug("metadata_not_found", repo_id=repo_id)
        return self._dict_to_meta(raw) if raw else None

    # ── Alias mapping ────────────────────────────────────────────────────────

    def save_alias(self, provisional_id: str, real_repo_id: str) -> None:
        """Save a mapping from a provisional job_id to a resolved real_repo_id."""
        logger.debug("saving_alias", provisional_id=provisional_id, real_repo_id=real_repo_id)
        path = self._alias_path(provisional_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"real_repo_id": real_repo_id}), encoding="utf-8")
        tmp.replace(path)

    def get_alias(self, provisional_id: str) -> str | None:
        """Return the real_repo_id for a provisional_id, if an alias exists."""
        path = self._alias_path(provisional_id)
        if not path.exists():
            return None
        try:
            real_id = json.loads(path.read_text(encoding="utf-8")).get("real_repo_id")
            logger.debug("alias_retrieved", provisional_id=provisional_id, real_repo_id=real_id)
            return real_id
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("alias_read_error", provisional_id=provisional_id, error=str(exc))
            return None

    # ── State transitions ─────────────────────────────────────────────────────

    def mark_pending(
        self,
        repo_id: str,
        repo_url: str,
        ref: str,
    ) -> RepoMetadata:
        """
        Transition to ``pending``.

        Must be called immediately after the ingestion lock is acquired and
        *before* any store (vector, graph) is touched.  This is the "dirty"
        sentinel — if the process crashes, downstream consumers refuse to
        serve the repo until it is re-ingested and marked ``synced``.
        """
        log = logger.bind(repo_id=repo_id)
        lock = self._get_repo_lock(repo_id)
        now = _utc_now()

        with lock:
            existing = self._read_raw(repo_id)
            old_status = existing.get("sync_status", "<none>") if existing else "<none>"
            try:
                from app.platform.tenant_context import get_tenant
                org_id = (existing or {}).get("org_id") or get_tenant().org_id
            except Exception:
                org_id = (existing or {}).get("org_id", "default")

            data: dict = {
                "repo_id": repo_id,
                "repo_url": repo_url,
                "ref": ref,
                "sync_status": "pending",
                "sync_started_at": now,
                "schema_version": SCHEMA_VERSION,
                "org_id": org_id,
                # Preserve previous clone info if re-ingesting
                "commit_hash": existing.get("commit_hash") if existing else None,
                "cloned_at": existing.get("cloned_at") if existing else None,
                "error_reason": None,
            }
            self._write_raw(repo_id, data)

        log.info(
            "sync_status_transition",
            old_status=old_status,
            new_status="pending",
        )
        return self._dict_to_meta(data)

    def mark_synced(
        self,
        repo_id: str,
        *,
        commit_hash: str,
        cloned_at: str,
    ) -> RepoMetadata:
        """
        Transition to ``synced``.

        Called by the ingestion orchestrator **only** after both the vector
        store (Module 6) and the graph store (Module 7) confirm successful
        writes.  Until both confirm, the repo stays ``pending``.

        Parameters
        ----------
        commit_hash:
            HEAD commit hexsha of the cloned repo.
        cloned_at:
            ISO-8601 UTC timestamp of when the clone completed.
        """
        log = logger.bind(repo_id=repo_id)
        lock = self._get_repo_lock(repo_id)

        with lock:
            raw = self._read_raw(repo_id)
            if raw is None:
                raise KeyError(f"No metadata record found for repo_id={repo_id!r}")
            old_status = raw.get("sync_status", "<none>")
            raw["sync_status"] = "synced"
            raw["commit_hash"] = commit_hash
            raw["cloned_at"] = cloned_at
            raw["error_reason"] = None
            self._write_raw(repo_id, raw)

        log.info(
            "sync_status_transition",
            old_status=old_status,
            new_status="synced",
            commit_hash=commit_hash,
        )
        return self._dict_to_meta(raw)

    def mark_failed(
        self,
        repo_id: str,
        *,
        error_reason: str,
    ) -> RepoMetadata:
        """
        Transition to ``failed``.

        Records the error reason so ``GET /status/{repo_id}`` (Module 12) can
        surface a human-readable explanation to the user.
        """
        log = logger.bind(repo_id=repo_id)
        lock = self._get_repo_lock(repo_id)

        with lock:
            raw = self._read_raw(repo_id)
            if raw is None:
                raise KeyError(f"No metadata record found for repo_id={repo_id!r}")
            old_status = raw.get("sync_status", "<none>")
            raw["sync_status"] = "failed"
            raw["error_reason"] = error_reason
            self._write_raw(repo_id, raw)

        log.info(
            "sync_status_transition",
            old_status=old_status,
            new_status="failed",
            error_reason=error_reason,
        )
        return self._dict_to_meta(raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Module-level singleton
#
#     from app.ingestion.metadata_store import metadata_store
# ---------------------------------------------------------------------------
metadata_store = MetadataStore()
