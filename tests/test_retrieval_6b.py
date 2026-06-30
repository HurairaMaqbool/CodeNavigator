"""
tests/test_retrieval_6b.py
--------------------------
Unit tests for Module 6b (Cross-Encoder, Query Expansion, and Final Assembly).

Run with:
    python -m unittest tests/test_retrieval_6b.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Bootstrap: mock structlog
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.config import settings
from app.parsing.chunker import CodeChunk
from app.retrieval.bm25_store import store_bm25
from app.retrieval.hybrid_search import FusedCandidate, search_code, dedup_by_file
from app.retrieval.query_expansion import _EXPANSION_CACHE, _normalize_cache_key, expand_query, needs_expansion
from app.retrieval.reranker import cross_encoder_rerank
from app.retrieval.vector_store import store_chunks


class DummyLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0

    def generate_text(self, prompt: str) -> str:
        self.call_count += 1
        if not self.responses:
            return '["sub query 1", "sub query 2"]'
        return self.responses.pop(0)


class TestQueryExpansion(unittest.TestCase):
    def setUp(self):
        _EXPANSION_CACHE.clear()
        
    def test_needs_expansion_gate(self):
        # Specific -> False
        self.assertFalse(needs_expansion("authenticate_user"))
        self.assertFalse(needs_expansion("validate token for jwt"))
        self.assertFalse(needs_expansion("def parseFile(path)"))
        self.assertFalse(needs_expansion('find "SELECT * FROM users"'))
        
        # Vague/Conceptual -> True (long, no quoted/camelCase/snake_case)
        self.assertTrue(needs_expansion("how does the system check if someone is logged in"))
        self.assertTrue(needs_expansion("explain the overall architecture for data ingestion"))

    def test_expand_query_makes_llm_call(self):
        llm = DummyLLM(['["auth flow", "login sequence"]'])
        query = "how does auth work over here"
        
        results = expand_query(query, llm)
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], query)
        self.assertEqual(results[1], "auth flow")

    def test_expand_query_uses_cache(self):
        llm = DummyLLM(['["one"]', '["two"]'])
        query = "how does auth work over here"
        
        res1 = expand_query(query, llm)
        res2 = expand_query(query + " ", llm)  # Trailing space
        
        self.assertEqual(llm.call_count, 1, "Second call must hit cache")
        self.assertEqual(res1, res2)


class TestDiversityCapping(unittest.TestCase):
    def test_dedup_by_file(self):
        candidates = [
            {"metadata": {"normalized_path": "a.py"}, "rerank_score": 0.9},
            {"metadata": {"normalized_path": "a.py"}, "rerank_score": 0.8},
            {"metadata": {"normalized_path": "b.py"}, "rerank_score": 0.7},
            {"metadata": {"normalized_path": "a.py"}, "rerank_score": 0.6}, # 3rd in a.py
        ]
        
        capped = dedup_by_file(candidates, max_per_file=2)
        
        self.assertEqual(len(capped), 3)
        self.assertEqual(capped[0]["metadata"]["normalized_path"], "a.py")
        self.assertEqual(capped[1]["metadata"]["normalized_path"], "a.py")
        self.assertEqual(capped[2]["metadata"]["normalized_path"], "b.py")
        
        # The 0.6 from a.py is gone
        scores = [c["rerank_score"] for c in capped]
        self.assertNotIn(0.6, scores)


class TestAssemblyIntegration(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.CHROMA_DB_PATH = os.path.join(self.td.name, "chroma")
        settings.BM25_INDEX_PATH = os.path.join(self.td.name, "bm25")
        settings.QUERY_EXPANSION_ENABLED = True
        
        import app.retrieval.vector_store
        app.retrieval.vector_store._CHROMA_CLIENT = None
        
        self.repo_id = "test_repo_6b"
        self.llm = DummyLLM(['["auth token", "jwt middleware"]'])

        # Create corpus
        self.chunks = [
            CodeChunk("def check_auth(): pass", "/a.py", "a.py", "a.py", "check_auth", 1, 1, "function", "python", "fp1", None),
            CodeChunk("def parse_jwt(): pass", "/a.py", "a.py", "a.py", "parse_jwt", 2, 2, "function", "python", "fp2", None),
            CodeChunk("def logout(): pass", "/a.py", "a.py", "a.py", "logout", 3, 3, "function", "python", "fp3", None),
            CodeChunk("def auth_middleware(): pass", "/b.py", "b.py", "b.py", "auth_middleware", 1, 1, "function", "python", "fp4", None),
            CodeChunk("def other(): pass", "/c.py", "c.py", "c.py", "other", 1, 1, "function", "python", "fp5", None),
        ]
        store_chunks(self.repo_id, self.chunks)
        store_bm25(self.repo_id, self.chunks)

    def tearDown(self):
        # Reset ChromaDB singleton so it releases file handles before cleanup
        import app.retrieval.vector_store as vs_mod
        if vs_mod._CHROMA_CLIENT is not None:
            try:
                vs_mod._CHROMA_CLIENT._producer.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        vs_mod._CHROMA_CLIENT = None
        self.td.cleanup()

    def test_search_code_specific_query_no_llm(self):
        # Should not trigger LLM due to snake_case "check_auth"
        results = search_code("check_auth", self.repo_id, self.llm, top_k=2)
        
        self.assertEqual(self.llm.call_count, 0)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["function_name"], "check_auth")
        self.assertIn("rerank_score", results[0])

    def test_search_code_vague_query_triggers_llm_and_diversity(self):
        # A long vague query
        query = "how does the system check if someone is logged in"
        
        results = search_code(query, self.repo_id, self.llm, top_k=5)
        
        # LLM should have been called
        self.assertEqual(self.llm.call_count, 1)
        
        # We have 3 chunks in a.py and 1 in b.py that relate to auth.
        # Diversity cap should limit a.py to 2 chunks max.
        a_py_count = sum(1 for r in results if r["metadata"]["display_path"] == "a.py")
        self.assertLessEqual(a_py_count, 2)
        
        # Should return available results (up to top_k=5, but we only have 5 total, capped to 2 from a.py -> max 4 possible returned)
        self.assertLessEqual(len(results), 4)

    def test_search_code_handles_small_candidate_pool(self):
        # Test edge case: small pool < 20 candidates.
        # Our corpus has 5 chunks. Cross-encoder shouldn't crash.
        results = search_code("something that matches none", self.repo_id, self.llm, top_k=10)
        # Even if BM25 matches nothing, vector search might pull everything with low scores.
        # It shouldn't crash.
        self.assertTrue(isinstance(results, list))

if __name__ == "__main__":
    unittest.main(verbosity=2)
