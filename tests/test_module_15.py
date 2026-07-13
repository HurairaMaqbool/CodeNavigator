# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_15.py
-----------------------
Test script for Module 15: Evaluation Layer
Checks zero-cost guarantees, ragas provider wiring, run_eval output, and compare_runs logic.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Mock heavy ML dependencies so we can test the logic without slow installs
from importlib.machinery import ModuleSpec

def create_mock_module(name):
    m = MagicMock()
    m.__spec__ = ModuleSpec(name, None)
    return m

_orig_modules = {
    k: sys.modules.get(k) for k in [
        "ragas", "ragas.llms", "ragas.embeddings", "ragas.metrics",
        "langchain_huggingface", "langchain_groq", "langchain_ollama", "datasets"
    ]
}

sys.modules["ragas"] = create_mock_module("ragas")
sys.modules["ragas.llms"] = create_mock_module("ragas.llms")
sys.modules["ragas.embeddings"] = create_mock_module("ragas.embeddings")
sys.modules["ragas.metrics"] = create_mock_module("ragas.metrics")
sys.modules["langchain_huggingface"] = create_mock_module("langchain_huggingface")
sys.modules["langchain_groq"] = create_mock_module("langchain_groq")
sys.modules["langchain_ollama"] = create_mock_module("langchain_ollama")
sys.modules["datasets"] = create_mock_module("datasets")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from eval.ragas_providers import get_judge_llm
from eval.compare_runs import compare_eval_runs

# Restore original modules immediately after imports
for k, orig in _orig_modules.items():
    if orig is not None:
        sys.modules[k] = orig
    else:
        sys.modules.pop(k, None)

class TestModule15(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Apply mocks during test execution
        for k in _orig_modules:
            sys.modules[k] = create_mock_module(k)

    @classmethod
    def tearDownClass(cls):
        # Restore original modules after test execution
        for k, orig in _orig_modules.items():
            if orig is not None:
                sys.modules[k] = orig
            else:
                sys.modules.pop(k, None)

    @patch.object(settings, "LLM_PROVIDER", "groq")
    @patch.object(settings, "GROQ_API_KEY", "")
    def test_fail_loudly_unconfigured_groq(self):
        """Step 2.2: The fail loudly if unconfigured test."""
        with self.assertRaisesRegex(ValueError, "GROQ_API_KEY is not set"):
            get_judge_llm()

    @patch.dict(os.environ, {"LLM_PROVIDER": "ollama"})
    @patch.object(settings, "LLM_PROVIDER", "ollama")
    def test_provider_consistency_ollama(self):
        """Step 2.4: Provider-consistency test for Ollama."""
        # we just mock the actual import of ChatOllama so it doesn't try to connect
        with patch("eval.ragas_providers.LangchainLLMWrapper") as mock_wrap:
            try:
                from langchain_community.chat_models import ChatOllama  # check if exists
                patch_path = "langchain_community.chat_models.ChatOllama"
            except ImportError:
                patch_path = "langchain_ollama.ChatOllama"
                
            with patch(patch_path) as mock_ollama:
                get_judge_llm()
                mock_ollama.assert_called_once()
                mock_wrap.assert_called_once()

    def test_zero_llm_calls_in_golden_set(self):
        """Step 5.3: Confirm zero LLM-as-judge calls inside test_golden_set.py."""
        golden_path = PROJECT_ROOT / "tests" / "test_golden_set.py"
        content = golden_path.read_text(encoding="utf-8")
        self.assertNotIn("evaluate(", content, "Found LLM-as-judge call in golden set!")
        self.assertNotIn("ragas", content, "Found ragas import in golden set!")

    def test_compare_runs_regression(self):
        """Step 4.2: compare_eval_runs on degraded metric."""
        history_path = PROJECT_ROOT / "tests" / "eval_history.jsonl"
        # Temporarily mock the load_history
        fake_history = [
            {"version": "v1", "ragas_scores": {"faithfulness": 0.90}, "mean_confidence_score": 8.0, "average_iterations": 2.0},
            {"version": "v2", "ragas_scores": {"faithfulness": 0.80}, "mean_confidence_score": 8.0, "average_iterations": 2.0},
            {"version": "v3", "ragas_scores": {"faithfulness": 0.90}, "mean_confidence_score": 8.0, "average_iterations": 5.0}, # degraded iterations
        ]
        with patch("eval.compare_runs.load_history", return_value=fake_history):
            res = compare_eval_runs("v1", "v2", tolerance=0.05)
            self.assertTrue(res["regressions_found"])
            self.assertEqual(res["regressions"][0]["metric"], "faithfulness")

            res_iter = compare_eval_runs("v1", "v3", tolerance=0.05)
            self.assertTrue(res_iter["regressions_found"])
            self.assertEqual(res_iter["regressions"][0]["metric"], "average_iterations")

    def test_compare_runs_missing(self):
        """Step 4.3: compare_eval_runs missing baseline."""
        with patch("eval.compare_runs.load_history", return_value=[]):
            with self.assertRaisesRegex(ValueError, "not found in history"):
                compare_eval_runs("non_existent", "v2")

    def test_docker_compose_bm25_volume(self):
        """Step 6.2: missing-volume check."""
        docker_path = PROJECT_ROOT / "docker-compose.yml"
        content = docker_path.read_text(encoding="utf-8")
        self.assertIn("bm25_data:/app/bm25_index", content, "BM25 persistence volume missing from docker-compose.yml!")

    def test_golden_set_gate_behavior(self):
        """Step 5.2: Deliberately break something and confirm the test catches it."""
        from tests.test_golden_set import test_golden_set_evaluation
        
        # We will mock run_eval to simulate a failure
        def mock_run_eval(*args, **kwargs):
            return {
                "eval_scores": {
                    "faithfulness": 0.50, # Below 0.80
                    "answer_relevancy": 0.90,
                    "context_precision": 0.90,
                    "context_recall": 0.90
                }
            }
            
        with patch("tests.test_golden_set.run_eval", side_effect=mock_run_eval):
            # Also mock Path.exists so the test doesn't skip if golden_set.json is missing
            with patch("tests.test_golden_set.Path.exists", return_value=True):
                with self.assertRaises(BaseException) as ctx:
                    test_golden_set_evaluation()
                self.assertIn("Golden Set metrics below targets", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
