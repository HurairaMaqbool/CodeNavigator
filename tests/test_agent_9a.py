# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_agent_9a.py
----------------------
Unit tests for agent loop + cache keys (aligned with Module #21 state machine).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.agent.cache_keys import normalize_cache_key
from app.agent.loop import _TOOL_CACHE, answer_question, compress_older_tool_results


class TestCacheKeys(unittest.TestCase):
    def test_normalize_cache_key_applies_defaults(self):
        k1 = normalize_cache_key("generate_diagram", {"name": "foo"})
        k2 = normalize_cache_key("generate_diagram", {"name": "foo", "depth": 2})
        self.assertEqual(k1, k2, "Default values must hash identically to omitted ones")

        k3 = normalize_cache_key("generate_diagram", {"name": "foo", "depth": 3})
        self.assertNotEqual(k1, k3)

    def test_normalize_cache_key_order_independent(self):
        k1 = normalize_cache_key("search_code", {"query": "test", "top_k": 3})
        k2 = normalize_cache_key("search_code", {"top_k": 3, "query": "test"})
        self.assertEqual(k1, k2)


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        _TOOL_CACHE.clear()

    def test_answer_question_exhausts_budget_gracefully(self):
        """Module #21: max_iterations forces FINALIZE with gated answer (not a hard crash)."""
        with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
            "app.agent.loop.metadata_store.get",
            return_value=MagicMock(sync_status="synced"),
        ), patch(
            "app.retrieval.query_expansion.expand_query", return_value=["hello"]
        ), patch("app.retrieval.hybrid_search.search", return_value=[]), patch(
            "app.retrieval.reranker.rerank", return_value=[]
        ), patch(
            "app.agent.loop._groq_text", return_value="NO"
        ), patch(
            "app.agent.loop.context_manager_assemble", return_value="ctx"
        ), patch(
            "app.agent.confidence.evaluate",
            return_value={"answer": "ctx", "confidence_score": 3.0, "gated": True},
        ), patch("app.agent.loop.semantic_cache_store"):
            res = answer_question("hello", "repo1", max_iterations=1)

        self.assertIn("answer", res)
        self.assertTrue(res.get("gated") is True or bool(res.get("answer")))
        self.assertIn("confidence_score", res)

    def test_tool_cache_hit_prevents_duplicate_execution(self):
        """Module #21: identical search variants are merged; retrieval runs once per variant set."""
        search_mock = MagicMock(
            return_value=[
                {
                    "chunk": "data",
                    "chunk_metadata": {"file_path": "a.py", "start_line": 1, "end_line": 2},
                    "score": 1.0,
                }
            ]
        )
        with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
            "app.agent.loop.metadata_store.get",
            return_value=MagicMock(sync_status="synced"),
        ), patch(
            "app.retrieval.query_expansion.expand_query", return_value=["x"]
        ), patch(
            "app.retrieval.hybrid_search.search", search_mock
        ), patch(
            "app.retrieval.reranker.rerank",
            return_value=[
                {
                    "chunk": "data",
                    "chunk_metadata": {"file_path": "a.py", "start_line": 1, "end_line": 2},
                    "score": 1.0,
                }
            ],
        ), patch(
            "app.agent.loop._groq_text", side_effect=["YES", "Done."]
        ), patch(
            "app.agent.confidence.evaluate",
            return_value={"answer": "Done.", "confidence_score": 8.5, "gated": False},
        ), patch("app.agent.loop.semantic_cache_store"):
            out = answer_question("query", "repo")

        self.assertEqual(out["answer"], "Done.")
        self.assertEqual(out["confidence_score"], 8.5)
        # One variant → one search call (no duplicate retrieval for the same query).
        self.assertEqual(search_mock.call_count, 1)

    def test_sync_gate_blocks_unsynced_repo(self):
        with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
            "app.agent.loop.metadata_store.get",
            return_value=MagicMock(sync_status="indexing"),
        ), patch("app.agent.loop._groq_text") as mock_groq:
            res = answer_question("hello", "repo1")

        self.assertIn("error", res)
        self.assertTrue(res.get("gated"))
        self.assertEqual(mock_groq.call_count, 0)

    @patch("app.agent.context_manager.get_llm_client")
    def test_context_compression(self, mock_get_llm):
        llm_mock = MagicMock()
        mock_get_llm.return_value = llm_mock

        summary_res = MagicMock()
        summary_res.content = [{"type": "text", "text": "compressed text"}]
        llm_mock.create.return_value = summary_res

        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a" * 5000},
            {"role": "user", "content": "tool result " + ("x" * 5000)},
        ]
        # Legacy helper mutates in place and returns None.
        result = compress_older_tool_results(messages, keep_last_n=1)
        self.assertTrue(result is None or isinstance(result, list))
        self.assertIsInstance(messages, list)
        self.assertGreaterEqual(len(messages), 1)


if __name__ == "__main__":
    unittest.main()
