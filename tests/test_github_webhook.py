# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_github_webhook.py
----------------------------
Unit tests for Module 13 (GitHub Webhook).

Run with:
    python -m unittest tests/test_github_webhook.py -v
"""
from __future__ import annotations

import hashlib
import hmac
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

from app.main import app
from app.config import settings
from app.ingestion.locking import LockResult

class TestGithubWebhook(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.old_secret = settings.GITHUB_WEBHOOK_SECRET
        settings.GITHUB_WEBHOOK_SECRET = "test_secret"

    def tearDown(self):
        settings.GITHUB_WEBHOOK_SECRET = self.old_secret
        
    def _sign(self, body_bytes: bytes, secret: str = "test_secret") -> str:
        return "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

    def test_missing_signature_401(self):
        resp = self.client.post("/webhook/github", json={})
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Missing", resp.json()["error"])

    def test_invalid_signature_401(self):
        body = b'{"ref": "refs/heads/main"}'
        headers = {"X-Hub-Signature-256": "sha256=invalidhash123"}
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid", resp.json()["error"])

    def test_duplicate_delivery_ignored(self):
        payload = {
            "ref": "refs/heads/main",
            "repository": {
                "default_branch": "main",
                "clone_url": "https://github.com/foo/bar.git",
            },
        }
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "dup-delivery-123",
        }
        with patch("app.webhook.github_webhook.trigger_ingest") as mock_trigger:
            mock_trigger.return_value = type("J", (), {"job_id": "x", "status": "processing"})()
            first = self.client.post("/webhook/github", content=body, headers=headers)
            second = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "accepted")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "ignored")
        self.assertIn("duplicate", second.json()["reason"])

    def test_non_push_ignored(self):
        body = json.dumps({"foo": "bar"}).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "pull_request"
        }
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.assertIn("not a push event", resp.json()["reason"])

    def test_non_default_branch_ignored(self):
        payload = {
            "ref": "refs/heads/feature-branch",
            "repository": {
                "default_branch": "main",
                "clone_url": "https://github.com/foo/bar.git"
            }
        }
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "push"
        }
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.assertIn("non-default branch", resp.json()["reason"])

    def test_malformed_payload_400(self):
        payload = {"random": "stuff"}
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "push"
        }
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Malformed", resp.json()["error"])

    @patch("app.webhook.github_webhook.trigger_ingest")
    def test_valid_push_triggers_ingest(self, mock_trigger):
        class MockJob:
            job_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            status = "processing"
            
        mock_trigger.return_value = MockJob()
        
        payload = {
            "ref": "refs/heads/main",
            "repository": {
                "default_branch": "main",
                "clone_url": "https://github.com/foo/bar.git"
            }
        }
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "push"
        }
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "accepted")
        self.assertEqual(resp.json()["job_id"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        
        mock_trigger.assert_called_once()
        args, kwargs = mock_trigger.call_args
        self.assertEqual(kwargs["repo_url"], "https://github.com/foo/bar.git")
        self.assertEqual(kwargs["ref"], "main")

    @patch("app.api.router.filter_repo_files")
    @patch("app.api.router.clone_repo")
    @patch("app.api.router.lock_manager.try_acquire")
    @patch("app.api.router.metadata_store.get_alias")
    def test_duplicate_delivery_already_running(self, mock_alias, mock_lock, mock_clone, mock_filter):
        # Test that the webhook returns "accepted" even when lock is already held
        from app.ingestion.clone import CloneResult
        from pathlib import Path
        mock_alias.return_value = None
        mock_lock.return_value = LockResult(acquired=False, repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        mock_clone.return_value = CloneResult(
            repo_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            clone_path=Path("dummy_path"),
            default_branch="main",
            commit_hash="1234567890abcdef1234567890abcdef12345678",
            size_bytes=100
        )
        mock_filter.return_value = [Path("dummy_path/main.py")]
        
        payload = {
            "ref": "refs/heads/main",
            "repository": {
                "default_branch": "main",
                "clone_url": "https://github.com/foo/bar.git"
            }
        }
        body = json.dumps(payload).encode()
        headers = {
            "X-Hub-Signature-256": self._sign(body),
            "X-GitHub-Event": "push"
        }
        
        resp = self.client.post("/webhook/github", content=body, headers=headers)
        self.assertEqual(resp.status_code, 200)
        # The webhook always returns "accepted" - the ingest_status field shows if it was already_running
        self.assertEqual(resp.json()["status"], "accepted")

if __name__ == "__main__":
    unittest.main(verbosity=2)
