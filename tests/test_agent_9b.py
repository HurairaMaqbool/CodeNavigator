# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_agent_9b.py
----------------------
Unit tests for Module 9b (Answer Validation & Confidence Scoring).

Run with:
    python -m unittest tests/test_agent_9b.py -v
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

from app.agent.confidence import (
    compute_confidence_score,
    extract_file_mentions_with_lines,
    extract_function_name_mentions,
    validate_and_return,
)

class TestCitations(unittest.TestCase):
    def test_extract_files(self):
        text = "Check `src/main.py:12` and `utils.js` and `app/config.ts:1-5`."
        files = extract_file_mentions_with_lines(text)
        self.assertEqual(files, [('src/main.py', 12, 12), ('utils.js', None, None), ('app/config.ts', 1, 5)])
        
    def test_extract_functions(self):
        text = "Call `authenticate_user()` or `self.auth.validate()`."
        funcs = extract_function_name_mentions(text)
        self.assertEqual(funcs, ["authenticate_user", "validate"])

class TestConfidenceScore(unittest.TestCase):
    def test_score_components(self):
        # 0 invalid ratio, top score 0.8, 2 citations
        # retrieval = 10 * 0.8 = 8.0 -> 0.50 * 8.0 = 4.0
        # grounding = 10 * 1 = 10 -> 0.35 * 10 = 3.5
        # citation = 2/3 * 10 = 6.666 -> 0.15 * 6.666 = 1.0
        # total = 4.0 + 3.5 + 1.0 = 8.5
        score = compute_confidence_score(0.0, 0.8, 2)
        self.assertEqual(score, 8.5)
        
    def test_score_zero_citations(self):
        # ratio None, retrieval 0.8, 0 citations
        # retrieval = 8.0 -> 4.0
        # grounding = 10 -> 3.5
        # citation = 0 -> 0
        # total = 7.5
        score1 = compute_confidence_score(None, 0.8, 0)
        
        # Proper citations is higher
        score2 = compute_confidence_score(0.0, 0.8, 3)
        self.assertLess(score1, score2)
        self.assertEqual(score1, 7.5)

    def test_score_graceful_degrade_none_retrieval(self):
        # None retrieval (e.g. used graph tool only)
        # retrieval = 0 -> 0
        # grounding = 10 -> 3.5
        # citation = 10 -> 1.5
        # total = 5.0
        score = compute_confidence_score(0.0, None, 3)
        self.assertEqual(score, 5.0)

class TestValidateAndReturn(unittest.TestCase):
    @patch("app.agent.confidence._load_repo_metadata")
    def test_fully_grounded_answer(self, mock_load):
        mock_load.return_value = [
            {"display_path": "src/auth.py", "function_name": "login", "start_line": 10, "end_line": 20}
        ]
        text = "The user logs in via `login()` in `src/auth.py`."
        content = [{"type": "text", "text": text}]
        
        res = validate_and_return(content, "repo", [], 0.9)
        
        self.assertFalse(res["gated"])
        self.assertEqual(res["invalid_reference_ratio"], 0.0)
        self.assertEqual(res["confidence"], "high")
        self.assertNotIn("warning", res)
        self.assertEqual(len(res["sources"]), 1)
        self.assertEqual(res["sources"][0]["file_path"], "src/auth.py")
        self.assertEqual(res["sources"][0]["function_name"], "login")

    @patch("app.agent.confidence._load_repo_metadata")
    def test_fully_fabricated_answer_gets_gated(self, mock_load):
        mock_load.return_value = []
        text = "I think it is `fake_func()` in `doesnt_exist.py:5`."
        content = [{"type": "text", "text": text}]
        
        res = validate_and_return(content, "repo", [], 0.1)
        
        self.assertTrue(res["gated"])
        # Original text should NOT be in the answer
        self.assertNotEqual(res["answer"], text)
        self.assertIn("could not find enough reliable context", res["answer"])
        self.assertEqual(res["invalid_reference_ratio"], 1.0) # 2 invalid / 2 total
        self.assertEqual(res.get("sources"), [])

    @patch("app.agent.confidence._load_repo_metadata")
    def test_partially_invalid_answer(self, mock_load):
        mock_load.return_value = [
            {"display_path": "src/real.py", "function_name": "real_func", "start_line": 1, "end_line": 5}
        ]
        text = "It uses `real_func()` in `src/real.py` but also `fake_func()` in `fake.py`."
        content = [{"type": "text", "text": text}]
        
        # High retrieval ensures it clears the gate despite partial hallucination
        res = validate_and_return(content, "repo", [], 0.99)
        
        self.assertFalse(res["gated"])
        self.assertEqual(res["invalid_reference_ratio"], 0.5) # 2 invalid / 4 total
        self.assertIn("warning", res)
        self.assertIn("fake_func", res["warning"])
        self.assertIn("fake.py", res["warning"])
        
        # Sources should only contain the valid one
        self.assertEqual(len(res["sources"]), 1)
        self.assertEqual(res["sources"][0]["file_path"], "src/real.py")

if __name__ == "__main__":
    unittest.main(verbosity=2)
