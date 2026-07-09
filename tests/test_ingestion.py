# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_ingestion.py
-----------------------
Unit tests for Module 3 (Ingestion Service).

All tests run WITHOUT network access and WITHOUT gitpython/filelock installed.
Every external boundary (git.Repo.clone_from, filelock, datetime.now) is
mocked so the test suite works immediately after cloning the repo.

Run with:
    pytest tests/test_ingestion.py -v
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Bootstrap: set LLM_PROVIDER=ollama before any app import so the config
# fail-fast guard for GROQ_API_KEY doesn't fire during tests.
# ---------------------------------------------------------------------------
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.pop("GROQ_API_KEY", None)

# Mock structlog so we don't need it installed to run unit tests
sys.modules["structlog"] = MagicMock()
sys.modules["structlog"].get_logger.return_value = MagicMock()


# ---------------------------------------------------------------------------
# Helpers to build a fake git.Repo object
# ---------------------------------------------------------------------------

def _make_fake_repo(
    branch_name: str = "main",
    commit_hexsha: str = "a" * 40,
) -> MagicMock:
    """Return a MagicMock that quacks like a git.Repo after clone_from."""
    repo = MagicMock()
    repo.active_branch.name = branch_name
    repo.head.commit.hexsha = commit_hexsha
    return repo


def _populate_tree(path: Path, files: dict[str, int] | None = None) -> None:
    """
    Create fake source files under *path* so _measure_tree_size has something
    to measure.

    *files* maps relative filename → size in bytes.
    """
    if files is None:
        files = {"main.py": 1024, "README.md": 512}
    for name, size in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * size)


# ===========================================================================
# A.  clone.py — repo_id computation
# ===========================================================================

class TestRepoIdFor(unittest.TestCase):

    def test_same_url_same_ref_is_deterministic(self):
        from app.ingestion.clone import repo_id_for
        rid1 = repo_id_for("https://github.com/owner/repo", "main")
        rid2 = repo_id_for("https://github.com/owner/repo", "main")
        self.assertEqual(rid1, rid2)

    def test_different_refs_give_different_ids(self):
        """The single most important invariant: branches must not share storage."""
        from app.ingestion.clone import repo_id_for
        rid_main = repo_id_for("https://github.com/owner/repo", "main")
        rid_dev  = repo_id_for("https://github.com/owner/repo", "dev")
        self.assertNotEqual(rid_main, rid_dev,
            "Two branches of the same repo MUST produce distinct repo_ids.")

    def test_different_urls_give_different_ids(self):
        from app.ingestion.clone import repo_id_for
        rid_a = repo_id_for("https://github.com/owner/repo-a", "main")
        rid_b = repo_id_for("https://github.com/owner/repo-b", "main")
        self.assertNotEqual(rid_a, rid_b)

    def test_repo_id_is_64_hex_chars(self):
        from app.ingestion.clone import repo_id_for
        rid = repo_id_for("https://github.com/owner/repo", "main")
        self.assertEqual(len(rid), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in rid))

    def test_trailing_slash_normalised(self):
        """URL with/without trailing slash must map to the same repo_id."""
        from app.ingestion.clone import repo_id_for
        rid1 = repo_id_for("https://github.com/owner/repo", "main")
        rid2 = repo_id_for("https://github.com/owner/repo/", "main")
        self.assertEqual(rid1, rid2)


# ===========================================================================
# B.  clone.py — URL validation
# ===========================================================================

class TestValidateUrl(unittest.TestCase):

    def _validate(self, url: str) -> None:
        from app.ingestion.clone import _validate_url
        _validate_url(url)

    def test_https_url_accepted(self):
        self._validate("https://github.com/owner/repo")

    def test_https_git_suffix_accepted(self):
        self._validate("https://github.com/owner/repo.git")

    def test_git_at_url_accepted(self):
        self._validate("git@github.com:owner/repo.git")

    def test_ssh_url_accepted(self):
        self._validate("ssh://git@github.com/owner/repo.git")

    def test_empty_string_rejected(self):
        from app.ingestion.clone import InvalidURLError
        with self.assertRaises(InvalidURLError):
            self._validate("")

    def test_plain_word_rejected(self):
        from app.ingestion.clone import InvalidURLError
        with self.assertRaises(InvalidURLError):
            self._validate("notaurl")

    def test_ftp_rejected(self):
        from app.ingestion.clone import InvalidURLError
        with self.assertRaises(InvalidURLError):
            self._validate("ftp://example.com/repo")


# ===========================================================================
# C.  clone.py — clone_repo error mapping
# ===========================================================================

class TestCloneRepoErrors(unittest.TestCase):
    """
    Each test patches git.Repo.clone_from to raise the appropriate GitCommandError
    and asserts that clone_repo translates it to the right IngestionError subtype.
    """

    def _make_git_cmd_err(self, stderr: str) -> Any:
        """Build a minimal git.GitCommandError stand-in."""
        err = MagicMock()
        err.stderr = stderr
        err.stdout = ""
        # Make it behave like git.exc.GitCommandError
        err.__class__.__name__ = "GitCommandError"
        return err

    def _patch_git(self, side_effect: Any):
        """Patch git.Repo.clone_from and _git_exc.GitCommandError."""
        git_mock = MagicMock()
        git_mock.Repo.clone_from.side_effect = side_effect
        git_exc_mock = MagicMock()
        git_exc_mock.GitCommandError = type(side_effect) if isinstance(side_effect, Exception) else Exception
        git_exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
        return git_mock, git_exc_mock

    def test_invalid_url_raises_invalid_url_error(self):
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import InvalidURLError, clone_repo
        with patch.object(clone_mod, "_GIT_AVAILABLE", True):
            with self.assertRaises(InvalidURLError):
                clone_repo("notaurl")

    def test_not_found_maps_to_repo_not_found_error(self):
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import RepoNotFoundError, clone_repo

        class FakeGitError(Exception):
            stderr = "Repository not found"
            stdout = ""

        with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock:
            exc_mock.GitCommandError = FakeGitError
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = FakeGitError("not found")

            with self.assertRaises(RepoNotFoundError):
                clone_repo("https://github.com/noone/nonexistent-repo-xyz")

    def test_auth_failure_maps_to_private_repo_error(self):
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import PrivateRepoError, clone_repo

        class FakeGitError(Exception):
            stderr = "Authentication failed for 'https://github.com/secret/repo'"
            stdout = ""

        with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock:
            exc_mock.GitCommandError = FakeGitError
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = FakeGitError("auth failed")

            with self.assertRaises(PrivateRepoError):
                clone_repo("https://github.com/secret/private-repo")

    def test_timeout_maps_to_network_timeout_error(self):
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import NetworkTimeoutError, clone_repo

        class FakeGitError(Exception):
            stderr = "Connection timed out after 60000 ms"
            stdout = ""

        with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock:
            exc_mock.GitCommandError = FakeGitError
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = FakeGitError("timed out")

            with self.assertRaises(NetworkTimeoutError):
                clone_repo("https://github.com/owner/repo")


class TestCloneRepoSuccess(unittest.TestCase):

    def _run_clone(self, tmp_path: Path, files: dict[str, int] | None = None,
                   branch: str = "main") -> Any:
        """
        Run clone_repo with git fully mocked.  Populates the temp clone dir
        with fake files so size measurement works.
        """
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import clone_repo

        fake_repo = _make_fake_repo(branch_name=branch)

        def fake_clone_from(url, dest, **kwargs):
            dest_path = Path(dest)
            dest_path.mkdir(parents=True, exist_ok=True)
            _populate_tree(dest_path, files)
            return fake_repo

        with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock:
            exc_mock.GitCommandError = type("GCE", (Exception,), {})
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = fake_clone_from

            return clone_repo(
                "https://github.com/owner/repo",
                base_dir=tmp_path,
            )

    def test_clone_result_fields_populated(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            result = self._run_clone(Path(td))
            self.assertIsNotNone(result.repo_id)
            self.assertEqual(result.default_branch, "main")
            self.assertEqual(result.commit_hash, "a" * 40)
            self.assertGreater(result.size_bytes, 0)
            self.assertTrue(result.clone_path.exists())

    def test_clone_path_is_under_base_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            result = self._run_clone(Path(td))
            self.assertTrue(str(result.clone_path).startswith(td))

    def test_repo_too_large_raises(self):
        import tempfile
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import RepoTooLargeError, clone_repo

        # 1 byte file but MAX_REPO_SIZE_MB patched to 0 MB
        fake_repo = _make_fake_repo()

        def fake_clone_from(url, dest, **kwargs):
            dest_path = Path(dest)
            dest_path.mkdir(parents=True, exist_ok=True)
            _populate_tree(dest_path, {"big.py": 1})
            return fake_repo

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, \
             patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock, \
             patch.object(clone_mod.settings, "MAX_REPO_SIZE_MB", 0):
            exc_mock.GitCommandError = type("GCE", (Exception,), {})
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = fake_clone_from

            with self.assertRaises(RepoTooLargeError) as ctx:
                clone_repo("https://github.com/owner/repo", base_dir=Path(td))

            self.assertGreater(ctx.exception.size_bytes, 0)
            self.assertEqual(ctx.exception.limit_mb, 0)

    def test_tmp_dir_cleaned_up_on_size_error(self):
        """No temp directories left on disk after a RepoTooLargeError."""
        import tempfile
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import RepoTooLargeError, clone_repo

        fake_repo = _make_fake_repo()

        def fake_clone_from(url, dest, **kwargs):
            dest_path = Path(dest)
            dest_path.mkdir(parents=True, exist_ok=True)
            _populate_tree(dest_path, {"f.py": 1})
            return fake_repo

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, \
             patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock, \
             patch.object(clone_mod.settings, "MAX_REPO_SIZE_MB", 0):
            exc_mock.GitCommandError = type("GCE", (Exception,), {})
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = fake_clone_from

            try:
                clone_repo("https://github.com/owner/repo", base_dir=Path(td))
            except RepoTooLargeError:
                pass

            # No _tmp_* directories should remain
            tmp_dirs = list(Path(td).glob("_tmp_*"))
            self.assertEqual(tmp_dirs, [],
                "Temp dirs not cleaned up after RepoTooLargeError")

    def test_two_branches_have_independent_paths(self):
        """
        Same URL, different branches → different repo_ids → different clone paths.
        This is the key isolation invariant.
        """
        import tempfile
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import clone_repo, repo_id_for

        def make_clone_fn(branch: str):
            fake_repo = _make_fake_repo(branch_name=branch)
            def fn(url, dest, **kwargs):
                Path(dest).mkdir(parents=True, exist_ok=True)
                _populate_tree(Path(dest))
                return fake_repo
            return fn

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            base = Path(td)

            for branch in ("main", "dev"):
                fake_clone = make_clone_fn(branch)
                with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
                     patch.object(clone_mod, "git") as git_mock, \
                     patch.object(clone_mod, "_git_exc") as exc_mock:
                    exc_mock.GitCommandError = type("GCE", (Exception,), {})
                    exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
                    git_mock.Repo.clone_from.side_effect = fake_clone
                    result = clone_repo(
                        "https://github.com/owner/repo",
                        ref=branch,
                        base_dir=base,
                    )
                    if branch == "main":
                        path_main = result.clone_path
                        rid_main  = result.repo_id
                    else:
                        path_dev = result.clone_path
                        rid_dev  = result.repo_id

            self.assertNotEqual(rid_main, rid_dev,
                "Same URL + different branch must yield different repo_ids")
            self.assertNotEqual(path_main, path_dev,
                "Same URL + different branch must yield different clone paths")
            # Confirm neither path is a parent/child of the other
            self.assertFalse(
                str(path_main).startswith(str(path_dev)) or
                str(path_dev).startswith(str(path_main)),
                "Clone paths must be completely independent",
            )


# ===========================================================================
# D.  metadata_store.py — state machine
# ===========================================================================

class TestMetadataStore(unittest.TestCase):

    def _make_store(self, tmp_path: Path) -> Any:
        from app.ingestion.metadata_store import MetadataStore
        return MetadataStore(base_dir=tmp_path)

    def test_get_returns_none_for_unknown_repo(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            self.assertIsNone(store.get("nonexistent_repo_id"))

    def test_mark_pending_creates_record(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            meta = store.mark_pending("repo1", "https://github.com/a/b", "main")
            self.assertEqual(meta.sync_status, "pending")
            self.assertEqual(meta.repo_url, "https://github.com/a/b")
            self.assertEqual(meta.ref, "main")
            self.assertIsNotNone(meta.sync_started_at)
            self.assertIsNone(meta.error_reason)
            from app.ingestion.metadata_store import SCHEMA_VERSION
            self.assertEqual(meta.schema_version, SCHEMA_VERSION)

    def test_mark_synced_transitions_correctly(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            store.mark_pending("repo1", "https://github.com/a/b", "main")
            meta = store.mark_synced(
                "repo1",
                commit_hash="b" * 40,
                cloned_at="2026-01-01T00:00:00+00:00",
            )
            self.assertEqual(meta.sync_status, "synced")
            self.assertEqual(meta.commit_hash, "b" * 40)
            self.assertIsNone(meta.error_reason)

    def test_mark_failed_transitions_correctly(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            store.mark_pending("repo1", "https://github.com/a/b", "main")
            meta = store.mark_failed("repo1", error_reason="disk full")
            self.assertEqual(meta.sync_status, "failed")
            self.assertEqual(meta.error_reason, "disk full")

    def test_get_reflects_latest_status(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            store.mark_pending("repo1", "https://github.com/a/b", "main")
            store.mark_synced("repo1", commit_hash="c" * 40,
                              cloned_at="2026-01-01T00:00:00+00:00")

            fetched = store.get("repo1")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.sync_status, "synced")

    def test_metadata_persisted_to_json_on_disk(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            store.mark_pending("repo42", "https://github.com/x/y", "feature")

            json_path = Path(td) / "repo42" / "metadata.json"
            self.assertTrue(json_path.exists(), "metadata.json must be on disk")
            data = json.loads(json_path.read_text())
            self.assertEqual(data["sync_status"], "pending")
            self.assertEqual(data["repo_url"], "https://github.com/x/y")
            self.assertEqual(data["ref"], "feature")

    def test_schema_version_stamped_on_every_record(self):
        import tempfile
        from app.ingestion.metadata_store import SCHEMA_VERSION
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            meta = store.mark_pending("r1", "https://g.com/o/r", "main")
            self.assertEqual(meta.schema_version, SCHEMA_VERSION)

    def test_mark_synced_on_missing_repo_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            with self.assertRaises(KeyError):
                store.mark_synced("ghost", commit_hash="a" * 40,
                                  cloned_at="2026-01-01T00:00:00+00:00")

    def test_mark_failed_on_missing_repo_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            with self.assertRaises(KeyError):
                store.mark_failed("ghost", error_reason="oops")

    def test_two_repos_are_independent(self):
        """Different repo_ids must not share metadata state."""
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            store = self._make_store(Path(td))
            store.mark_pending("repo-A", "https://g.com/a/a", "main")
            store.mark_pending("repo-B", "https://g.com/b/b", "main")
            store.mark_synced("repo-A", commit_hash="a" * 40,
                              cloned_at="2026-01-01T00:00:00+00:00")

            a = store.get("repo-A")
            b = store.get("repo-B")
            self.assertEqual(a.sync_status, "synced")
            self.assertEqual(b.sync_status, "pending",
                "Marking repo-A synced must not affect repo-B")


# ===========================================================================
# E.  locking.py — concurrency and stale-lock recovery
# ===========================================================================

class TestRepoLockManager(unittest.TestCase):

    def _make_manager_and_store(self, tmp_path: Path):
        from app.ingestion.locking import RepoLockManager
        from app.ingestion.metadata_store import MetadataStore
        # Fresh instances so tests don't share in-process lock state
        mgr = RepoLockManager()
        store = MetadataStore(base_dir=tmp_path)
        return mgr, store

    # ── Basic acquire / release ───────────────────────────────────────────────

    def test_first_acquire_succeeds(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))
            result = mgr.try_acquire("repo-1", store)
            self.assertTrue(result.acquired)
            self.assertFalse(result.stale_override)
            mgr.release("repo-1")

    def test_second_acquire_blocked_while_first_held(self):
        """
        Two concurrent ingest calls for the same repo_id:
        the second must get acquired=False, not start a parallel job.
        """
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            r1 = mgr.try_acquire("repo-1", store)
            self.assertTrue(r1.acquired, "First acquire must succeed")

            r2 = mgr.try_acquire("repo-1", store)
            self.assertFalse(r2.acquired,
                "Second acquire for same repo_id must fail while first is held")

            mgr.release("repo-1")

    def test_acquire_succeeds_after_release(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            mgr.try_acquire("repo-1", store)
            mgr.release("repo-1")

            r = mgr.try_acquire("repo-1", store)
            self.assertTrue(r.acquired,
                "Acquire should succeed once the previous lock is released")
            mgr.release("repo-1")

    def test_different_repos_dont_block_each_other(self):
        """Locks are keyed by repo_id — unrelated repos must be independent."""
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            r_a = mgr.try_acquire("repo-A", store)
            r_b = mgr.try_acquire("repo-B", store)
            self.assertTrue(r_a.acquired)
            self.assertTrue(r_b.acquired,
                "Lock on repo-A must not block repo-B")
            mgr.release("repo-A")
            mgr.release("repo-B")

    # ── already_running semantics ─────────────────────────────────────────────

    def test_second_acquire_carries_existing_started_at(self):
        """
        When the second caller gets acquired=False it should receive the first
        job's sync_started_at so the API layer can include it in the response.
        """
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))
            store.mark_pending("repo-1", "https://g.com/o/r", "main")

            mgr.try_acquire("repo-1", store)
            r2 = mgr.try_acquire("repo-1", store)

            self.assertFalse(r2.acquired)
            self.assertIsNotNone(r2.existing_started_at,
                "Second caller must receive the existing job's sync_started_at")
            mgr.release("repo-1")

    # ── Stale-lock recovery ───────────────────────────────────────────────────

    def test_stale_pending_record_allows_new_acquire(self):
        """
        Core crash-recovery scenario:
        1. A previous worker set sync_status=pending with an old sync_started_at.
        2. The process crashed; its threading.Lock is gone.
        3. A new request arrives.
        4. The TTL has expired → the new request must be allowed through
           with stale_override=True.

        This is implemented by writing a metadata record with a sync_started_at
        that is older than INGEST_PENDING_TTL_SECONDS and confirming the lock
        manager grants the new acquire.
        """
        import tempfile
        from app.ingestion import locking as lock_mod

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            # Simulate a crashed worker: write a stale pending record directly.
            old_time = (
                datetime.now(timezone.utc) - timedelta(seconds=10_000)
            ).isoformat()
            store._write_raw("repo-crashed", {
                "repo_id": "repo-crashed",
                "repo_url": "https://g.com/o/r",
                "ref": "main",
                "sync_status": "pending",
                "sync_started_at": old_time,
                "schema_version": 1,
                "commit_hash": None,
                "cloned_at": None,
                "error_reason": None,
            })

            # TTL is 900 s by default; our record is 10,000 s old → stale.
            result = mgr.try_acquire("repo-crashed", store)

            self.assertTrue(result.acquired,
                "Stale pending record must allow a new acquire")
            self.assertTrue(result.stale_override,
                "stale_override must be True when overriding a crashed job")
            mgr.release("repo-crashed")

    def test_fresh_pending_record_blocks_new_acquire(self):
        """
        A pending record within the TTL means the job is legitimately running;
        the new request must NOT proceed.
        """
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            # Write a fresh pending record (just started)
            fresh_time = datetime.now(timezone.utc).isoformat()
            store._write_raw("repo-running", {
                "repo_id": "repo-running",
                "repo_url": "https://g.com/o/r",
                "ref": "main",
                "sync_status": "pending",
                "sync_started_at": fresh_time,
                "schema_version": 1,
                "commit_hash": None,
                "cloned_at": None,
                "error_reason": None,
            })

            # Simulate the first request holding the lock
            mgr.try_acquire("repo-running", store)

            # Second request arrives while lock is held and record is fresh
            result = mgr.try_acquire("repo-running", store)
            self.assertFalse(result.acquired,
                "Fresh pending record must block a concurrent new acquire")
            mgr.release("repo-running")

    def test_release_allows_reacquire_after_stale_override(self):
        """After a stale-override acquire is released, a subsequent acquire works."""
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))

            old_time = (
                datetime.now(timezone.utc) - timedelta(seconds=10_000)
            ).isoformat()
            store._write_raw("repo-x", {
                "repo_id": "repo-x",
                "repo_url": "https://g.com/o/r",
                "ref": "main",
                "sync_status": "pending",
                "sync_started_at": old_time,
                "schema_version": 1,
                "commit_hash": None,
                "cloned_at": None,
                "error_reason": None,
            })

            r1 = mgr.try_acquire("repo-x", store)
            self.assertTrue(r1.acquired)
            self.assertTrue(r1.stale_override)
            mgr.release("repo-x")

            r2 = mgr.try_acquire("repo-x", store)
            self.assertTrue(r2.acquired,
                "Should be acquirable again after stale override is released")
            mgr.release("repo-x")

    # ── Thread-safety smoke test ──────────────────────────────────────────────

    def test_concurrent_threads_only_one_acquires(self):
        """
        Fire N threads simultaneously; exactly ONE must get acquired=True.
        This is the multi-thread regression for the "two concurrent /ingest
        calls" scenario.
        """
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            mgr, store = self._make_manager_and_store(Path(td))
            results: list[bool] = []
            barrier = threading.Barrier(8)

            def worker():
                barrier.wait()          # all threads start at the same instant
                r = mgr.try_acquire("shared-repo", store)
                results.append(r.acquired)
                if r.acquired:
                    time.sleep(0.05)    # hold the lock briefly
                    mgr.release("shared-repo")

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            acquired_count = sum(1 for r in results if r)
            self.assertEqual(acquired_count, 1,
                f"Exactly 1 thread should acquire the lock; got {acquired_count}")


# ===========================================================================
# F.  Integration: clone + metadata state machine flow
# ===========================================================================

class TestIngestionFlow(unittest.TestCase):
    """
    Exercises the full Module 3 flow (without network):
    clone_repo → mark_pending → (work...) → mark_synced / mark_failed
    """

    def _mock_clone(self, base_dir: Path, branch: str = "main") -> Any:
        from app.ingestion import clone as clone_mod
        from app.ingestion.clone import clone_repo

        fake_repo = _make_fake_repo(branch_name=branch)

        def fake_clone_from(url, dest, **kwargs):
            Path(dest).mkdir(parents=True, exist_ok=True)
            _populate_tree(Path(dest))
            return fake_repo

        with patch.object(clone_mod, "_GIT_AVAILABLE", True), \
             patch.object(clone_mod, "git") as git_mock, \
             patch.object(clone_mod, "_git_exc") as exc_mock:
            exc_mock.GitCommandError = type("GCE", (Exception,), {})
            exc_mock.InvalidGitRepositoryError = type("IGE", (Exception,), {})
            git_mock.Repo.clone_from.side_effect = fake_clone_from
            return clone_repo("https://github.com/owner/small-repo",
                              base_dir=base_dir)

    def test_full_happy_path_ends_in_synced(self):
        import tempfile
        from app.ingestion.metadata_store import MetadataStore
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            base = Path(td)
            store = MetadataStore(base_dir=base)

            # 1. Clone
            result = self._mock_clone(base)

            # 2. Immediately mark pending (as the ingest orchestrator would)
            store.mark_pending(result.repo_id, "https://github.com/owner/small-repo", result.default_branch)
            meta = store.get(result.repo_id)
            self.assertEqual(meta.sync_status, "pending")

            # 3. Simulate successful downstream writes (Modules 6 + 7)
            store.mark_synced(
                result.repo_id,
                commit_hash=result.commit_hash,
                cloned_at=datetime.now(timezone.utc).isoformat(),
            )
            meta = store.get(result.repo_id)
            self.assertEqual(meta.sync_status, "synced")
            self.assertTrue(result.clone_path.exists())

    def test_full_failure_path_ends_in_failed(self):
        import tempfile
        from app.ingestion.metadata_store import MetadataStore
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            base = Path(td)
            store = MetadataStore(base_dir=base)

            result = self._mock_clone(base)
            store.mark_pending(result.repo_id, "https://github.com/owner/small-repo", result.default_branch)
            store.mark_failed(result.repo_id, error_reason="vector store write failed")

            meta = store.get(result.repo_id)
            self.assertEqual(meta.sync_status, "failed")
            self.assertEqual(meta.error_reason, "vector store write failed")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
