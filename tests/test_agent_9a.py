# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_agent_9a.py
----------------------
Unit tests for Module 9a (Agent Loop & Caching).

Run with:
    python -m unittest tests/test_agent_9a.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Bootstrap: mock structlog
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.agent.cache_keys import normalize_cache_key
from app.agent.loop import _TOOL_CACHE, answer_question, compress_older_tool_results

class TestCacheKeys(unittest.TestCase):
    def test_normalize_cache_key_applies_defaults(self):
        # generate_diagram has depth: 2 as default
        k1 = normalize_cache_key("generate_diagram", {"name": "foo"})
        k2 = normalize_cache_key("generate_diagram", {"name": "foo", "depth": 2})
        self.assertEqual(k1, k2, "Default values must hash identically to omitted ones")
        
        k3 = normalize_cache_key("generate_diagram", {"name": "foo", "depth": 3})
        self.assertNotEqual(k1, k3)

    def test_normalize_cache_key_order_independent(self):
        # Search code top_k=5
        k1 = normalize_cache_key("search_code", {"query": "test", "top_k": 3})
        k2 = normalize_cache_key("search_code", {"top_k": 3, "query": "test"})
        self.assertEqual(k1, k2)


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        _TOOL_CACHE.clear()

    @patch("app.agent.loop.get_llm_client")
    @patch("app.agent.loop.execute_tool_with_retry")
    def test_answer_question_exhausts_budget_gracefully(self, mock_exec, mock_get_llm):
        llm_mock = MagicMock()
        mock_get_llm.return_value = llm_mock
        
        # Force LLM to always request a tool
        mock_res = MagicMock()
        mock_res.stop_reason = "tool_use"
        mock_res.content = [{"type": "tool_use", "id": "t1", "name": "search_code", "input": {"query": "x"}}]
        mock_res.usage = {"input_tokens": 10, "output_tokens": 10}
        llm_mock.create.return_value = mock_res
        
        mock_exec.return_value = {"results": []}
        
        # Max iterations is 5
        res = answer_question("hello", "repo1", max_iterations=2, max_tool_calls=5)
        
        # Fell out of loop
        self.assertIn("error", res)
        self.assertEqual(res["error"], "Could not resolve within the iteration limit.")
        
        self.assertEqual(llm_mock.create.call_count, 2)

    @patch("app.agent.loop.get_llm_client")
    @patch("app.agent.loop.execute_tool_with_retry")
    def test_tool_cache_hit_prevents_duplicate_execution(self, mock_exec, mock_get_llm):
        llm_mock = MagicMock()
        mock_get_llm.return_value = llm_mock
        
        # Turn 1: Call search_code
        res1 = MagicMock()
        res1.stop_reason = "tool_use"
        res1.content = [{"type": "tool_use", "id": "t1", "name": "search_code", "input": {"query": "x"}}]
        res1.usage = {}
        
        # Turn 2: Call search_code with EXACT SAME input
        res2 = MagicMock()
        res2.stop_reason = "tool_use"
        res2.content = [{"type": "tool_use", "id": "t2", "name": "search_code", "input": {"query": "x"}}]
        res2.usage = {}
        
        # Turn 3: End
        res3 = MagicMock()
        res3.stop_reason = "end_turn"
        res3.content = [{"type": "text", "text": "Done."}]
        res3.usage = {}
        
        llm_mock.create.side_effect = [res1, res2, res3]
        mock_exec.return_value = {"results": [{"chunk": "data", "rerank_score": 1.0}]}
        
        with patch("app.agent.loop._prefetch_context", return_value=(None, [{"rerank_score": 1.0}], 1.0)):
            out = answer_question("query", "repo")
        
        self.assertEqual(out["answer"], "Done.")
        self.assertEqual(out["confidence_score"], 8.5)
        
        # execute_tool_with_retry should only be called ONCE despite two tool calls
        self.assertEqual(mock_exec.call_count, 1)

    @patch("app.agent.context_manager.get_llm_client")
    def test_context_compression(self, mock_get_llm):
        # Provide a dummy LLM for compression
        llm_mock = MagicMock()
        mock_get_llm.return_value = llm_mock
        
        summary_res = MagicMock()
        summary_res.content = [{"type": "text", "text": "compressed text"}]
        llm_mock.create.return_value = summary_res
        
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": [{"type": "tool_use"}]},
            # Old result 1
            {"role": "user", "content": [{"type": "tool_result", "content": "massive output 1"}]},
            {"role": "assistant", "content": [{"type": "tool_use"}]},
            # Old result 2
            {"role": "user", "content": [{"type": "tool_result", "content": "massive output 2"}]},
            {"role": "assistant", "content": [{"type": "tool_use"}]},
            # Recent result (keep_last_n=1 for this test to force compression of 1 and 2)
            {"role": "user", "content": [{"type": "tool_result", "content": "recent output"}]},
        ]
        
        compress_older_tool_results(messages, keep_last_n=1)
        
        # The first two tool results should be replaced with text blocks
        self.assertEqual(messages[2]["content"][0]["type"], "text")
        self.assertIn("Compressed prior tool results", messages[2]["content"][0]["text"])
        self.assertEqual(messages[4]["content"][0]["type"], "text")
        self.assertIn("Compressed prior tool results", messages[4]["content"][0]["text"])
        
        # The last one is untouched
        self.assertEqual(messages[6]["content"][0]["type"], "tool_result")


if __name__ == "__main__":
    unittest.main(verbosity=2)
