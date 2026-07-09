# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/ingestion/metadata_store.py
--------------------------------
Persistent per-repo lifecycle tracking — the ingestion state machine record.

State machine (Module #9 spec)
-------------------------------
Every ingested repository passes through the following stages in order:

    PENDING -> CLONING -> FILTERING -> PARSING -> INDEXING -> SYNCED
                                                       |
                                          any stage -> FAILED

Each stage writes an explicit checkpoint via update() before handing off.
On failure, update(stage=FAILED, error=...) is called and the stage is NOT
marked complete.  On retry, last_checkpoint() returns the last successfully
completed stage so the pipeline can resume from the correct point.

Storage
-------
JSON-file-backed, one file per repository::

    {REPOS_PATH}/{repo_id}/metadata.json

Assumption: the spec says "shelve-backed dictionary".  This implementation
uses atomic JSON files instead of Python's shelve module.  JSON was chosen
because: (a) existing tests rely on it, (b) it is human-readable for debugging,
(c) shelve has platform-dependent file naming (.db/.dir/.bak) and is not
atomic.  The behaviour is identical from the caller's perspective.

Thread safety
~~~~~~~~~~~~~
A per-repo threading.Lock guards reads and writes so concurrent async
requests for the same repo_id see a consistent view.  locking.py (Module #6)
guarantees single-writer access at the ingestion level, so write contention
only arises from concurrent read/status requests.

Public API
----------
    from app.ingestion.metadata_store import metadata_store, Stage, RepoMetadata

    # Unified idempotent checkpoint write (spec-required)
    metadata_store.update(repo_id, Stage.CLONING, commit_hash="abc123")
    metadata_store.update(repo_id, Stage.FAILED, error="clone failed")

    # Resume-on-retry
    last = metadata_store.last_checkpoint(repo_id)  # -> Stage

    # Read (used by /status and agent loop)
    meta: RepoMetadata | None = metadata_store.get(repo_id)
    if meta is None or meta.sync_status != "synced":
        raise ...  # refuse to serve /chat until fully indexed

    # Stage-specific convenience methods (backward compat, still used internally)
    metadata_store.mark_pending(repo_id, repo_url, ref)
    metadata_store.mark_synced(repo_id, commit_hash=..., cloned_at=...)
    metadata_store.mark_failed(repo_id, error_reason="...")
"""
from __future__ import annotations

import enum
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.config import settings
from app.observability.logging_config import logger


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 1
"""
Increment this constant whenever the index format changes (e.g. new chunking
strategy, embedding model swap, graph schema change).  Every new metadata
record is stamped with the current value.  Future modules compare it to detect
stale indexes that need re-ingestion.
"""


# ---------------------------------------------------------------------------
# Stage enum  (Module #9 spec requirement)
# ---------------------------------------------------------------------------

class Stage(str, enum.Enum):
    """
    Ordered ingestion pipeline stages.

    Each stage is a string so it round-trips cleanly through JSON and can be
    compared directly against the ``sync_status`` field stored on disk.

    Ordering is significant: stages earlier in the list are considered
    "before" stages later in the list, which is used by last_checkpoint()
    to find the resume point on retry.
    """
    PENDING   = "pending"
    CLONING   = "cloning"
    FILTERING = "filtering"
    PARSING   = "parsing"
    INDEXING  = "indexing"
    SYNCED    = "synced"
    FAILED    = "failed"

    # Ordered sequence for checkpoint comparison (FAILED is never a resume point)
    @classmethod
    def ordered(cls) -> list["Stage"]:
        """Return stages in pipeline order, excluding FAILED."""
        return [cls.PENDING, cls.CLONING, cls.FILTERING, cls.PARSING, cls.INDEXING, cls.SYNCED]


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
    sync_status: str                 # one of Stage enum values
    schema_version: int              # always SCHEMA_VERSION at write time

    # Set once the clone completes
    commit_hash: str | None = None
    cloned_at: str | None = None     # ISO-8601 UTC

    # Set the moment the lock is acquired (pending transition)
    sync_started_at: str | None = None  # ISO-8601 UTC

    # Set on failed transition
    error_reason: str | None = None

    # File count recorded by file_filter.py (FILTERING stage)
    file_count: int | None = None

    # Graph builder (Module #18) sets this when circular imports are detected
    has_circular_dependencies: bool = False

    # Last successfully completed Stage (for resume-on-retry)
    # Stored as a string to survive JSON round-trip; cast to Stage on read
    last_stage: str | None = None

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
            file_count=d.get("file_count"),
            has_circular_dependencies=d.get("has_circular_dependencies", False),
            last_stage=d.get("last_stage"),
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

    # ── Spec-required unified API (Module #9) ────────────────────────────────

    def update(
        self,
        repo_id: str,
        stage: Stage,
        *,
        commit_hash: str | None = None,
        error: str | None = None,
        progress: str | None = None,
        has_circular_dependencies: bool | None = None,
    ) -> None:
        """
        Idempotent checkpoint write for a pipeline stage transition.

        This is the **primary** write API introduced by Module #9.  Every
        pipeline stage calls this before handing off to the next stage.

        Parameters
        ----------
        repo_id:
            Repository identifier (slug hash, from clone.py).
        stage:
            The Stage the pipeline has just completed (or FAILED).
        commit_hash:
            HEAD commit SHA — supplied on CLONING and SYNCED transitions.
        error:
            Human-readable failure reason — supplied only on FAILED transitions.
        progress:
            Optional progress description (e.g. "Processed 5/10 files") saved in the record.

        Idempotency
        -----------
        Calling update() twice with the same (repo_id, stage) is safe:
        - FAILED: error_reason is overwritten (last error wins — deliberate).
        - All other stages: checkpoint fields are written again, values unchanged.

        The stage is NOT marked complete if it is FAILED:
        - last_stage is NOT updated.
        - sync_status is set to "failed".
        This is the spec-required behaviour for resume-on-retry.

        Single-writer assumption
        ------------------------
        Concurrent writes to the same repo_id are prevented upstream by
        locking.py (Module #6).  This method does NOT implement its own
        inter-process lock — do not call it outside the ingestion pipeline
        without holding the ingestion lock first.
        """
        log = logger.bind(repo_id=repo_id, stage=stage.value)
        lock = self._get_repo_lock(repo_id)

        with lock:
            raw = self._read_raw(repo_id)
            if raw is None:
                # Bootstrap a minimal record if none exists (e.g. called before
                # mark_pending — should not happen in normal flow, but be safe).
                raw = {
                    "repo_id": repo_id,
                    "repo_url": "",
                    "ref": "HEAD",
                    "sync_status": stage.value,
                    "schema_version": SCHEMA_VERSION,
                    "org_id": "default",
                }

            if stage is Stage.FAILED:
                # Record failure without advancing last_stage
                raw["sync_status"] = Stage.FAILED.value
                raw["error_reason"] = error or "unknown error"
                log.warning("stage_transition_failed", error=raw["error_reason"])
            else:
                # Successful stage: update sync_status and last_stage
                raw["sync_status"] = stage.value
                raw["last_stage"] = stage.value
                raw["error_reason"] = None  # clear any previous failure
                if progress is not None:
                    raw["parsing_progress"] = progress
                if commit_hash is not None:
                    raw["commit_hash"] = commit_hash
                    raw["cloned_at"] = raw.get("cloned_at") or _utc_now()
                if has_circular_dependencies is not None:
                    raw["has_circular_dependencies"] = has_circular_dependencies
                log.info("stage_transition_ok", new_stage=stage.value)

            self._write_raw(repo_id, raw)

    def last_checkpoint(self, repo_id: str) -> Stage:
        """
        Return the last successfully completed :class:`Stage` for *repo_id*.

        Used by the retry / resume logic: after a failure, the ingestion
        orchestrator calls this to find the last good stage and restarts from
        the *next* stage rather than from the beginning.

        Returns
        -------
        Stage.PENDING
            If no checkpoint has been recorded yet (repo was never processed or
            only mark_pending() has been called).

        Examples
        --------
        If the pipeline crashed during PARSING (after FILTERING succeeded):
            last_checkpoint("repo-abc") -> Stage.FILTERING

        The orchestrator then resumes from PARSING instead of CLONING.
        """
        lock = self._get_repo_lock(repo_id)
        with lock:
            raw = self._read_raw(repo_id)

        if raw is None:
            return Stage.PENDING

        last = raw.get("last_stage")
        if last is None:
            return Stage.PENDING

        try:
            return Stage(last)
        except ValueError:
            logger.warning(
                "unknown_last_stage_value",
                repo_id=repo_id,
                raw_value=last,
            )
            return Stage.PENDING

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
            raw["last_stage"] = Stage.SYNCED.value   # advance resume-on-retry checkpoint
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

    def mark_cloned(
        self,
        repo_id: str,
        *,
        commit_hash: str,
        cloned_at: str,
    ) -> RepoMetadata:
        """
        Record that the repository has been successfully cloned (CLONED checkpoint).
        Keeps the sync_status as 'pending' but updates commit_hash and cloned_at.
        """
        log = logger.bind(repo_id=repo_id)
        lock = self._get_repo_lock(repo_id)

        with lock:
            raw = self._read_raw(repo_id)
            if raw is None:
                raise KeyError(f"No metadata record found for repo_id={repo_id!r}")
            raw["commit_hash"] = commit_hash
            raw["cloned_at"] = cloned_at
            raw["last_stage"] = Stage.CLONING.value  # advance resume-on-retry checkpoint
            self._write_raw(repo_id, raw)

        log.info(
            "sync_status_cloned_checkpoint",
            commit_hash=commit_hash,
            cloned_at=cloned_at,
        )
        return self._dict_to_meta(raw)

    def mark_filtered(
        self,
        repo_id: str,
        *,
        file_count: int,
    ) -> RepoMetadata:
        """
        Record that file filtering completed (FILTERED checkpoint).
        Keeps sync_status as 'pending' but records file_count for diagnostics.
        Called by file_filter.py (Module #8) after filter_repo_files() completes.
        """
        log = logger.bind(repo_id=repo_id)
        lock = self._get_repo_lock(repo_id)

        with lock:
            raw = self._read_raw(repo_id)
            if raw is None:
                raise KeyError(f"No metadata record found for repo_id={repo_id!r}")
            raw["file_count"] = file_count
            raw["last_stage"] = Stage.FILTERING.value  # advance resume-on-retry checkpoint
            self._write_raw(repo_id, raw)

        log.info("sync_status_filtered_checkpoint", file_count=file_count)
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
