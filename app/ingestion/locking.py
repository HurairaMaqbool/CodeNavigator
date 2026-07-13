# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/ingestion/locking.py
------------------------
Process-local + file-based concurrency control for ingestion jobs.

Design
------
The project runs on a single machine with a single uvicorn worker (explicit
out-of-scope: distributed locking / horizontal scaling).  Concurrency arises
from async request handling within the single process.

Two-layer locking strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~
1. In-process ``threading.Lock`` per repo_id — guarantees two concurrent async
   requests for the *same* repo_id don't both proceed through the clone/index
   pipeline at the same time within one process.

2. ``filelock.FileLock`` per repo_id — guards against accidental multi-process
   runs (e.g. a developer running two uvicorn instances locally).

Stale-lock recovery
~~~~~~~~~~~~~~~~~~~
If a worker crashes mid-ingest the threading.Lock disappears with the process,
but the metadata record stays at ``sync_status=pending`` with an old
``sync_started_at``.  When a new request arrives for that repo_id:

  - If ``sync_started_at`` is older than ``settings.INGEST_PENDING_TTL_SECONDS``
    (default 900 s / 15 min): treat the pending record as stale, allow the new
    request to proceed, and set ``stale_override=True`` on the returned result.
  - Otherwise: the job is still legitimately running; return ``acquired=False``.

Usage
-----
    from app.ingestion.locking import lock_manager
    from app.ingestion.metadata_store import metadata_store

    result = lock_manager.try_acquire(repo_id, metadata_store)
    if not result.acquired:
        return {"status": "already_running", "repo_id": repo_id}
    try:
        # ... do the actual ingestion work ...
    finally:
        lock_manager.release(repo_id)
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import filelock as _fl
    _FileLock = _fl.FileLock
    _Timeout = _fl.Timeout
    _FILELOCK_AVAILABLE = True
except ImportError:
    # filelock is in requirements.txt; this branch is only hit before
    # ``pip install -r requirements.txt`` has been run.
    _FileLock = None  # type: ignore[assignment, misc]
    _Timeout = Exception  # type: ignore[assignment, misc]
    _FILELOCK_AVAILABLE = False

from app.config import settings
from app.ingestion.metadata_store import Stage
from app.observability.logging_config import logger

if TYPE_CHECKING:
    from app.ingestion.metadata_store import MetadataStore


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class LockResult:
    """Result of a :meth:`RepoLockManager.try_acquire` call."""
    acquired: bool
    repo_id: str
    stale_override: bool = False
    # Set to the existing job's sync_started_at when acquired=False,
    # so the API layer can surface it in the "already running" response.
    existing_started_at: str | None = None


# ---------------------------------------------------------------------------
# Lock manager
# ---------------------------------------------------------------------------

class RepoLockManager:
    """
    Manages per-repo ingestion locks.

    Thread-safety: all mutations to ``_locks`` and ``_file_locks`` go through
    ``_registry_lock``.
    """

    def __init__(self) -> None:
        self._registry_lock: threading.Lock = threading.Lock()
        # repo_id → threading.Lock (in-process, one per repo)
        self._locks: dict[str, threading.Lock] = {}
        # repo_id → filelock.FileLock (cross-process, optional)
        self._file_locks: dict[str, Any] = {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_thread_lock(self, repo_id: str) -> threading.Lock:
        """Return the existing threading.Lock for *repo_id*, or create one."""
        with self._registry_lock:
            if repo_id not in self._locks:
                self._locks[repo_id] = threading.Lock()
            return self._locks[repo_id]

    def _drop_thread_lock(self, repo_id: str) -> None:
        """Remove the threading.Lock entry for *repo_id* entirely.

        Used during stale-lock recovery so a fresh (unacquired) lock is created
        on the next call to ``_get_thread_lock``.
        """
        with self._registry_lock:
            self._locks.pop(repo_id, None)

    def _lock_file_path(self, repo_id: str) -> Path:
        return Path(settings.REPOS_PATH) / repo_id / "ingest.lock"

    def _release_file_lock(self, repo_id: str) -> None:
        """Release and discard the filelock for *repo_id* (best-effort)."""
        if not _FILELOCK_AVAILABLE:
            return
        with self._registry_lock:
            fl = self._file_locks.pop(repo_id, None)
        if fl is not None:
            try:
                fl.release(force=True)
            except Exception:  # noqa: BLE001
                pass

    def _acquire_file_lock(self, repo_id: str) -> bool:
        """Try to acquire the filelock.  Returns False if already held."""
        if not _FILELOCK_AVAILABLE:
            return True  # treat as success when filelock not installed
        lock_path = self._lock_file_path(repo_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fl = _FileLock(str(lock_path))
        try:
            fl.acquire(timeout=0)
        except _Timeout:
            return False
        with self._registry_lock:
            self._file_locks[repo_id] = fl
        return True

    # ── Public API ────────────────────────────────────────────────────────────

    def try_acquire(
        self,
        repo_id: str,
        metadata_store: "MetadataStore",
    ) -> LockResult:
        """
        Attempt to acquire the ingestion lock for *repo_id*.

        Algorithm
        ---------
        1. Check metadata for a stale ``pending`` record (crashed-process recovery).
           If stale: force-clear the thread lock entry so step 2 creates a fresh one.
        2. Try to acquire the per-repo threading.Lock (non-blocking).
           Failure here means another *in-process* coroutine is already ingesting.
        3. Try to acquire the filelock (non-blocking, timeout=0).
           Failure here means another OS process holds the lock.

        Returns
        -------
        LockResult
            ``acquired=True``  → caller may proceed with ingestion.
            ``acquired=False`` → another job is running; caller should return
                                 ``{"status": "already_running", ...}`` to the client.
        """
        log = logger.bind(repo_id=repo_id)
        is_stale = False

        # ── Step 1: Stale-lock detection ──────────────────────────────────────
        meta = metadata_store.get(repo_id)
        if (
            meta is not None
            and Stage.is_pending(meta.sync_status)
            and meta.sync_started_at is not None
        ):
            try:
                started_at = datetime.fromisoformat(meta.sync_started_at)
                # Ensure timezone-aware comparison
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                age_s = (datetime.now(timezone.utc) - started_at).total_seconds()
                ttl = settings.INGEST_PENDING_TTL_SECONDS

                if age_s > ttl:
                    is_stale = True
                    log.warning(
                        "stale_lock_detected",
                        age_seconds=int(age_s),
                        ttl_seconds=ttl,
                    )
                    # Drop the thread-lock entry so step 2 creates a clean one.
                    self._drop_thread_lock(repo_id)
                    # Release any lingering file lock from a dead process.
                    self._release_file_lock(repo_id)
            except (ValueError, OverflowError):
                pass  # malformed sync_started_at — ignore, proceed normally

        # ── Step 2: In-process threading.Lock ────────────────────────────────
        thread_lock = self._get_thread_lock(repo_id)
        acquired = thread_lock.acquire(blocking=False)

        if not acquired:
            log.info(
                "lock_already_held",
                existing_started_at=meta.sync_started_at if meta else None,
            )
            return LockResult(
                acquired=False,
                repo_id=repo_id,
                existing_started_at=meta.sync_started_at if meta else None,
            )

        # ── Step 3: File lock (cross-process) ─────────────────────────────────
        if not self._acquire_file_lock(repo_id):
            # Another OS process has the lock — back off.
            thread_lock.release()
            log.warning("lock_held_by_another_process")
            return LockResult(acquired=False, repo_id=repo_id)

        log.info("lock_acquired", stale_override=is_stale)
        return LockResult(acquired=True, repo_id=repo_id, stale_override=is_stale)

    def release(self, repo_id: str) -> None:
        """
        Release both the threading.Lock and the filelock for *repo_id*.

        Safe to call multiple times — subsequent calls on an already-released
        lock are logged as warnings rather than raised as errors.
        """
        log = logger.bind(repo_id=repo_id)

        # Release filelock first (it's the outer guard).
        self._release_file_lock(repo_id)

        # Release threading.Lock.
        with self._registry_lock:
            thread_lock = self._locks.get(repo_id)

        if thread_lock is None:
            log.warning("lock_release_called_but_no_lock_registered")
            return

        try:
            thread_lock.release()
            log.info("lock_released")
        except RuntimeError:
            log.warning("lock_release_called_but_not_held")


# ---------------------------------------------------------------------------
# Module-level wrappers for spec compatibility (Layer 3 Ingestion Pipeline)
# ---------------------------------------------------------------------------

def acquire_lock(repo_id: str) -> bool:
    """
    Acquire the ingestion lock for *repo_id* (non-blocking).

    This wraps the process-local lock_manager, passing the default metadata_store.
    If scaled to multiple worker nodes, this upgrades to a Redis-backed distributed
    lock with the same public interface.
    """
    from app.ingestion.metadata_store import metadata_store
    res = lock_manager.try_acquire(repo_id, metadata_store)
    return res.acquired


def release_lock(repo_id: str) -> None:
    """
    Release the ingestion lock for *repo_id*.
    """
    lock_manager.release(repo_id)


# ---------------------------------------------------------------------------
# Module-level singleton — import and use directly.
#
#     from app.ingestion.locking import lock_manager
# ---------------------------------------------------------------------------
lock_manager = RepoLockManager()

