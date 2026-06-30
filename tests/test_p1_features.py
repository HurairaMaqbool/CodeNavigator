"""
tests/test_p1_features.py
-------------------------
Tests for P1 improvements: Redis job store, webhook hardening, config.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("LLM_PROVIDER", "ollama")

from app.config import Settings
from app.jobs.eval_job_store import get_eval_job, set_eval_job
from app.webhook.delivery_guard import is_duplicate_delivery, reset_delivery_guard


class TestWebhookConfig(unittest.TestCase):
    def test_effective_webhook_secret_alias(self):
        s = Settings(
            GROQ_API_KEY="test-key-for-settings",
            LLM_PROVIDER="groq",
            GITHUB_WEBHOOK_SECRET=None,
            WEBHOOK_SECRET="alias-secret",
        )
        self.assertEqual(s.effective_webhook_secret(), "alias-secret")

    def test_production_requires_webhook_secret(self):
        with self.assertRaises(ValueError):
            Settings(
                GROQ_API_KEY="test-key",
                LLM_PROVIDER="groq",
                ENVIRONMENT="production",
                GITHUB_WEBHOOK_SECRET="",
                WEBHOOK_SECRET="",
            )


class TestDeliveryGuard(unittest.TestCase):
    def setUp(self):
        reset_delivery_guard()

    def test_duplicate_delivery_in_memory(self):
        self.assertFalse(is_duplicate_delivery("delivery-1"))
        self.assertTrue(is_duplicate_delivery("delivery-1"))

    def test_empty_delivery_not_duplicate(self):
        self.assertFalse(is_duplicate_delivery(None))
        self.assertFalse(is_duplicate_delivery(""))


class TestEvalJobStore(unittest.TestCase):
    def test_set_and_get_job(self):
        job_id = "test-job-p1-001"
        set_eval_job(job_id, status="queued", result=None)
        set_eval_job(job_id, status="done", result={"version": "abc"})
        job = get_eval_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"]["version"], "abc")


if __name__ == "__main__":
    unittest.main()
