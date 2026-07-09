# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_semantic_cache.py
----------------------------
Unit tests for Module 10 (Semantic Cache).

Run with:
    python -m unittest tests/test_semantic_cache.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app.agent.semantic_cache

class MockInvalidCollectionException(Exception):
    pass

_chroma_mock = MagicMock()
_chroma_mock.errors.InvalidCollectionException = MockInvalidCollectionException
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()

from app.config import settings
from app.agent.semantic_cache import (
    SemanticCache,
    answer_question_cached,
    sweep_expired_entries,
)

class TestSemanticCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("LLM_PROVIDER", "ollama")
        cls._original_structlog = sys.modules.get("structlog")
        sys.modules["structlog"] = _structlog_mock
        cls._original_chromadb = getattr(app.agent.semantic_cache, "chromadb", None)
        app.agent.semantic_cache.chromadb = _chroma_mock

    @classmethod
    def tearDownClass(cls):
        app.agent.semantic_cache.chromadb = cls._original_chromadb
        if cls._original_structlog is not None:
            sys.modules["structlog"] = cls._original_structlog
        else:
            sys.modules.pop("structlog", None)

    def setUp(self):
        # We will mock the collection
        self.mock_col = MagicMock()
        self.mock_col.count.return_value = 1
        self.mock_client = MagicMock()
        self.mock_client.get_collection.return_value = self.mock_col
        self.mock_client.create_collection.return_value = self.mock_col
        _chroma_mock.PersistentClient.return_value = self.mock_client

    def _passthrough_refresh(self, cached, question, repo_id):
        out = dict(cached)
        out.setdefault("sources", [])
        return out

    @patch("app.agent.semantic_cache.embed")
    @patch("app.agent.semantic_cache.answer_question")
    @patch("app.agent.semantic_cache._get_repo_metadata")
    def test_cache_miss_stores_and_returns_false(self, mock_get_meta, mock_answer, mock_embed):
        mock_get_meta.return_value = {"commit_hash": "abc"}
        mock_embed.return_value = [0.1, 0.2]
        mock_answer.return_value = {"answer": "real answer", "gated": False}
        
        # Force a miss by making the collection return no results
        self.mock_col.count.return_value = 0
        self.mock_col.query.return_value = {"ids": [], "distances": [], "metadatas": []}
        
        res = answer_question_cached("How does it work?", "repo1")
        
        self.assertEqual(res["answer"], "real answer")
        self.assertFalse(res["cache_hit"])
        
        # Should have stored it
        self.mock_col.add.assert_called_once()
        args = self.mock_col.add.call_args[1]
        self.assertEqual(args["metadatas"][0]["repo_commit_hash"], "abc")

    @patch("app.agent.semantic_cache.embed")
    @patch("app.agent.semantic_cache.answer_question")
    @patch("app.agent.semantic_cache._get_repo_metadata")
    def test_cache_hit(self, mock_get_meta, mock_answer, mock_embed):
        mock_get_meta.return_value = {"commit_hash": "abc"}
        mock_embed.return_value = [0.1, 0.2]
        
        # Simulate a hit with similarity 0.99 (distance 0.01)
        self.mock_col.count.return_value = 1
        self.mock_col.query.return_value = {
            "ids": [["cache_1"]], 
            "distances": [[0.01]], 
            "metadatas": [[{
                "answer_json": json.dumps({"answer": "cached answer", "gated": False}),
                "repo_commit_hash": "abc",
                "timestamp": int(time.time())
            }]]
        }
        
        with patch("app.agent.semantic_cache._refresh_cached_answer", side_effect=self._passthrough_refresh):
            res = answer_question_cached("How does it work?", "repo1")
        
        self.assertEqual(res["answer"], "cached answer")
        self.assertTrue(res["cache_hit"])
        self.assertEqual(mock_answer.call_count, 0) # Skipped pipeline!

    @patch("app.agent.semantic_cache.embed")
    @patch("app.agent.semantic_cache.answer_question")
    @patch("app.agent.semantic_cache._get_repo_metadata")
    def test_stale_commit_hash_forces_miss(self, mock_get_meta, mock_answer, mock_embed):
        # Current commit is "def"
        mock_get_meta.return_value = {"commit_hash": "def"}
        mock_embed.return_value = [0.1, 0.2]
        mock_answer.return_value = {"answer": "new answer", "gated": False}
        
        # Cached entry is for commit "abc"
        self.mock_col.query.return_value = {
            "ids": [["cache_1"]], 
            "distances": [[0.01]], 
            "metadatas": [[{
                "answer_json": json.dumps({"answer": "cached answer"}),
                "repo_commit_hash": "abc"  # STALE!
            }]]
        }
        
        res = answer_question_cached("How does it work?", "repo1")
        
        self.assertEqual(res["answer"], "new answer") # Pulled from real pipeline
        self.assertFalse(res["cache_hit"])

    @patch("app.agent.semantic_cache.embed")
    @patch("app.agent.semantic_cache.answer_question")
    @patch("app.agent.semantic_cache._get_repo_metadata")
    def test_gated_answers_never_cached(self, mock_get_meta, mock_answer, mock_embed):
        mock_get_meta.return_value = {"commit_hash": "abc"}
        mock_embed.return_value = [0.1, 0.2]
        mock_answer.return_value = {"answer": "refusal", "gated": True}
        
        self.mock_col.count.return_value = 0
        self.mock_col.query.return_value = {"ids": []}
        
        res = answer_question_cached("How?", "repo1")
        
        self.assertEqual(res["answer"], "refusal")
        self.assertFalse(res["cache_hit"])
        
        # Should NOT have stored it
        self.mock_col.add.assert_not_called()

    @patch("app.agent.semantic_cache.embed")
    @patch("app.agent.semantic_cache.answer_question")
    @patch("app.agent.semantic_cache._get_repo_metadata")
    def test_semantic_cache_disabled(self, mock_get_meta, mock_answer, mock_embed):
        old_val = settings.SEMANTIC_CACHE_ENABLED
        settings.SEMANTIC_CACHE_ENABLED = False
        
        try:
            mock_answer.return_value = {"answer": "disabled answer", "gated": False}
            res = answer_question_cached("How?", "repo1")
            
            self.assertEqual(res["answer"], "disabled answer")
            self.assertFalse(res["cache_hit"])
            
            # Embed wasn't even called
            self.assertEqual(mock_embed.call_count, 0)
            self.mock_col.query.assert_not_called()
        finally:
            settings.SEMANTIC_CACHE_ENABLED = old_val

    def test_sweep_expired(self):
        sweep_expired_entries("repo1")
        self.mock_col.delete.assert_called_once()
        args = self.mock_col.delete.call_args[1]
        self.assertIn("where", args)
        self.assertIn("timestamp", args["where"])
        self.assertIn("$lt", args["where"]["timestamp"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
