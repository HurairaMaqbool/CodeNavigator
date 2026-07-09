# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_api_endpoints.py
---------------------------
Unit tests for Module 12 FastAPI endpoints.

Run with:
    python -m unittest tests/test_api_endpoints.py -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Bootstrap: mock structlog before importing app
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

# Mock ChromaDB before importing semantic_cache
_chroma_mock = MagicMock()


from app.main import app
from app.ingestion.clone import CloneResult
from app.ingestion.locking import LockResult
from app.ingestion.metadata_store import metadata_store, RepoMetadata
from app.api.router import IngestRequest

from app.api.auth import verify_api_key

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides[verify_api_key] = lambda: None
        self.bg_patcher = patch("fastapi.BackgroundTasks.add_task")
        self.mock_add_task = self.bg_patcher.start()

    def tearDown(self):
        self.bg_patcher.stop()
        app.dependency_overrides.clear()

    @patch("app.tasks.ingestion_task.run_ingestion.delay")
    @patch("app.api.router.lock_manager.try_acquire")
    @patch("app.api.router.metadata_store.mark_pending")
    @patch("app.api.router.metadata_store.get_alias")
    def test_ingest_successful_start(self, mock_alias, mock_pending, mock_lock, mock_delay):
        """POST /ingest returns 202 immediately with a job_id (async pipeline design)."""
        mock_alias.return_value = None  # No pre-existing alias
        mock_lock.return_value = LockResult(acquired=True, repo_id="repo123")
        mock_delay.return_value = MagicMock(id="test-task-id")

        app.dependency_overrides[verify_api_key] = lambda: None
        resp = self.client.post("/ingest", json={"repo_url": "https://github.com/foo/bar"})

        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["status"], "processing")
        mock_pending.assert_called_once()
        mock_delay.assert_called_once()

    @patch("app.api.router.lock_manager.try_acquire")
    @patch("app.api.router.metadata_store.get_alias")
    def test_ingest_already_running_returns_200(self, mock_alias, mock_lock):
        """POST /ingest returns 200 with already_running when lock is not acquired."""
        mock_alias.return_value = None
        mock_lock.return_value = LockResult(acquired=False, repo_id="repo123")

        app.dependency_overrides[verify_api_key] = lambda: None
        resp = self.client.post("/ingest", json={"repo_url": "https://github.com/foo/bar"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "already_running")

    @patch("app.api.router.metadata_store.get")
    @patch("app.api.router.metadata_store.get_alias")
    def test_chat_rejects_unsynced(self, mock_alias, mock_meta_get):
        mock_alias.return_value = None  # No alias resolution
        mock_meta_get.return_value = RepoMetadata(
            repo_id="repo123",
            repo_url="x",
            ref="main",
            sync_status="pending",
            schema_version=1
        )

        resp = self.client.post("/chat", json={"repo_id": "repo123", "question": "hello?"})

        self.assertEqual(resp.status_code, 409)
        self.assertIn("ingestion incomplete (status: pending)", resp.json()["error"])

    @patch("app.api.router.metadata_store.get")
    @patch("app.api.router.run")
    @patch("app.api.router.metadata_store.get_alias")
    def test_chat_success(self, mock_alias, mock_answer, mock_meta_get):
        mock_alias.return_value = None
        mock_meta_get.return_value = RepoMetadata(
            repo_id="repo123",
            repo_url="x",
            ref="main",
            sync_status="synced",
            schema_version=1
        )
        mock_answer.return_value = {
            "answer": "Yes.",
            "sources": [],
            "confidence": "high",
            "confidence_score": 9.5,
            "invalid_reference_ratio": 0.0,
            "gated": False,
            "cache_hit": True
        }

        resp = self.client.post("/chat", json={"repo_id": "repo123", "question": "hello?"})

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["cache_hit"])
        self.assertEqual(resp.json()["answer"], "Yes.")

    def test_global_exception_handler(self):
        # Force an unexpected error in an endpoint → 500 JSON with "error" key
        with patch("app.api.router.metadata_store.get", side_effect=ValueError("Boom")):
            resp = self.client.get("/status/repo123")
            self.assertEqual(resp.status_code, 500)
            self.assertEqual(resp.json()["error"], "An unexpected server error occurred. Please check the logs.")

    @patch("app.api.router.metadata_store.get")
    @patch("app.api.router.run")
    @patch("app.api.router.metadata_store.get_alias")
    def test_chat_rate_limit_returns_429(self, mock_alias, mock_answer, mock_meta_get):
        """POST /chat returns 429 (safety-net path) when RateLimitError escapes the loop."""
        from app.agent.llm_client import RateLimitError
        mock_alias.return_value = None
        mock_meta_get.return_value = RepoMetadata(
            repo_id="repo123",
            repo_url="x",
            ref="main",
            sync_status="synced",
            schema_version=1
        )
        mock_answer.side_effect = RateLimitError("Groq API rate limit exceeded.")

        resp = self.client.post("/chat", json={"repo_id": "repo123", "question": "hello?"})

        self.assertEqual(resp.status_code, 429)
        self.assertIn("rate", resp.json()["detail"].lower())

    @patch("app.api.router.metadata_store.get")
    @patch("app.api.router.run")
    @patch("app.api.router.metadata_store.get_alias")
    def test_chat_rate_limited_dict_returns_429(self, mock_alias, mock_answer, mock_meta_get):
        """POST /chat returns 429 (primary path) when the loop returns rate_limited=True dict."""
        mock_alias.return_value = None
        mock_meta_get.return_value = RepoMetadata(
            repo_id="repo123",
            repo_url="x",
            ref="main",
            sync_status="synced",
            schema_version=1
        )
        # Simulate the graceful rate-limit dict returned by loop.py after retry exhausted
        mock_answer.return_value = {
            "answer": "The AI provider is temporarily rate-limited. Please wait about 30 seconds and try again.",
            "sources": [],
            "confidence": "low",
            "confidence_score": 0.0,
            "invalid_reference_ratio": None,
            "gated": True,
            "rate_limited": True,
            "trace": [],
        }

        resp = self.client.post("/chat", json={"repo_id": "repo123", "question": "hello?"})

        self.assertEqual(resp.status_code, 429)
        detail = resp.json()["detail"].lower()
        self.assertIn("rate-limited", detail)
        self.assertIn("30 seconds", detail)

    @patch("app.api.router.metadata_store.get")
    @patch("app.api.router.run")
    @patch("app.api.router.metadata_store.get_alias")
    def test_chat_timed_out_returns_504(self, mock_alias, mock_answer, mock_meta_get):
        """POST /chat returns 504 when the loop returns timed_out=True dict."""
        mock_alias.return_value = None
        mock_meta_get.return_value = RepoMetadata(
            repo_id="repo123",
            repo_url="x",
            ref="main",
            sync_status="synced",
            schema_version=1
        )
        # Simulate the graceful timeout dict returned by loop.py
        mock_answer.return_value = {
            "answer": "The request took too long to complete. Please try again in a moment.",
            "sources": [],
            "confidence": "low",
            "confidence_score": 0.0,
            "invalid_reference_ratio": None,
            "gated": True,
            "timed_out": True,
            "trace": [],
        }

        resp = self.client.post("/chat", json={"repo_id": "repo123", "question": "hello?"})

        self.assertEqual(resp.status_code, 504)
        detail = resp.json()["detail"].lower()
        self.assertIn("took too long", detail)

if __name__ == "__main__":
    unittest.main(verbosity=2)
