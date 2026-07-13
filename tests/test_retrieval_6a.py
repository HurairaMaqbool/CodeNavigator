# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_retrieval_6a.py
--------------------------
Unit tests for Module 6a (Vector Store, BM25, Hybrid RRF).

Run with:
    python -m unittest tests/test_retrieval_6a.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Bootstrap: mock structlog and setup test paths
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock

from app.config import settings
from app.parsing.chunker import CodeChunk
from app.retrieval.bm25_store import search_bm25, store_bm25
from app.retrieval.embeddings import embed, embed_batch
from app.retrieval.hybrid_search import search_hybrid
from app.retrieval.vector_store import ModelMismatchError, search_vectors, store_chunks


class TestEmbeddings(unittest.TestCase):
    def test_embed_single(self):
        vec = embed("hello world")
        self.assertIsInstance(vec, list)
        self.assertGreater(len(vec), 10)  # usually 384 for all-MiniLM

    def test_embed_batch(self):
        vecs = embed_batch(["one", "two"])
        self.assertEqual(len(vecs), 2)
        self.assertEqual(len(vecs[0]), len(vecs[1]))


class TestVectorAndBM25Store(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        settings.CHROMA_DB_PATH = os.path.join(self.td.name, "chroma")
        settings.BM25_INDEX_PATH = os.path.join(self.td.name, "bm25")
        
        # Reset the Chroma client singleton so tests don't leak state
        import app.retrieval.vector_store
        app.retrieval.vector_store._CHROMA_CLIENT = None
        
        self.repo_id = "test_repo_123"

        # Create dummy chunks
        self.chunks = [
            CodeChunk(
                chunk_text="def foo():\n    return 'vector_target'",
                file_path="/a/b.py", display_path="b.py", normalized_path="b.py",
                function_name="foo", start_line=1, end_line=2, type="function",
                language="python", fingerprint="fp1", class_name=None
            ),
            CodeChunk(
                chunk_text="def XYZ123():\n    return 'unique_identifier'",
                file_path="/a/c.py", display_path="c.py", normalized_path="c.py",
                function_name="XYZ123", start_line=1, end_line=2, type="function",
                language="python", fingerprint="fp2", class_name=None
            ),
            CodeChunk(
                chunk_text="def dummy():\n    pass",
                file_path="/a/dummy.py", display_path="dummy.py", normalized_path="dummy.py",
                function_name="dummy", start_line=1, end_line=2, type="function",
                language="python", fingerprint="dummy_fp", class_name=None
            ),
        ]

    def tearDown(self):
        # Reset ChromaDB singleton and delete collection so it releases file handles before cleanup
        import app.retrieval.vector_store as vs_mod
        if vs_mod._CHROMA_CLIENT is not None:
            try:
                vs_mod._CHROMA_CLIENT.delete_collection(vs_mod._collection_name_for(self.repo_id))
            except Exception:
                pass
            try:
                vs_mod._CHROMA_CLIENT._producer.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        vs_mod._CHROMA_CLIENT = None
        self.td.cleanup()

    def test_store_and_search_vector(self):
        store_chunks(self.repo_id, self.chunks)
        results = search_vectors(self.repo_id, "semantic query for vector_target", n_results=1)
        self.assertEqual(len(results), 1)
        # We assert rank order (it returned the right one), not raw floats.
        self.assertEqual(results[0].id, "chunk_fp1")

    def test_store_and_search_bm25(self):
        store_bm25(self.repo_id, self.chunks)
        # Search for exact token XYZ123
        results = search_bm25(self.repo_id, "XYZ123", top_n=2)
        self.assertEqual(len(results), 1)  # Only one match for that specific token
        self.assertEqual(results[0].id, "chunk_fp2")

    def test_model_mismatch_raises_error(self):
        store_chunks(self.repo_id, self.chunks)
        
        # Simulate config change
        old_model = settings.EMBEDDING_MODEL
        settings.EMBEDDING_MODEL = "different-model-id"
        
        try:
            with self.assertRaises(ModelMismatchError):
                store_chunks(self.repo_id, self.chunks)
                
            # Wiping bypasses the error
            store_chunks(self.repo_id, self.chunks, force_reindex=True)
        finally:
            settings.EMBEDDING_MODEL = old_model

    def test_hybrid_search_fusion(self):
        store_chunks(self.repo_id, self.chunks)
        store_bm25(self.repo_id, self.chunks)
        
        # Query that should hit fp1 via vector, fp2 via BM25 exact match
        # Actually, let's just use RRF to pull the entire corpus and ensure dedup.
        fused = search_hybrid(self.repo_id, "XYZ123 vector_target", n_results=2)
        self.assertEqual(len(fused), 2)
        
        # The FusedCandidate should have scores and IDs
        ids = [f.id for f in fused]
        self.assertIn("chunk_fp1", ids)
        self.assertIn("chunk_fp2", ids)
        
        # Assert each appears only once (dedup)
        self.assertEqual(len(set(ids)), 2)

    def test_zero_vector_hits_handled_gracefully(self):
        # Even if vector search returned nothing (e.g., collection empty, though Chroma
        # usually always returns *something* if collection has items), BM25 should still work.
        # Let's test the BM25-only scenario by mocking vector store to return [].
        store_bm25(self.repo_id, self.chunks)
        fused = search_hybrid(self.repo_id, "XYZ123", n_results=5)
        # No vectors stored, vector search returns [], BM25 returns fp2.
        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0].id, "chunk_fp2")
        self.assertIsNone(fused[0].vector_rank)
        self.assertIsNotNone(fused[0].bm25_rank)


if __name__ == "__main__":
    unittest.main(verbosity=2)
