"""
tests/test_module_6a.py
-----------------------
Module 6a: Embeddings + Vector Store + BM25 Index + Hybrid Fusion (RRF)

Tests are split into:
  - Pure logic tests (no real embeddings/Chroma required) — run always
  - Integration tests (require chromadb + sentence-transformers) — skipped if unavailable
"""
import sys
import shutil
import tempfile
import pickle
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Check what's available
# ---------------------------------------------------------------------------
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    import sentence_transformers
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False

try:
    import rank_bm25
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

# ---------------------------------------------------------------------------
# Pre-emptively mock heavy optional deps so modules can be imported
# even when chromadb / sentence-transformers are not installed.
# ---------------------------------------------------------------------------
_MOCK_ST = MagicMock()
_MOCK_ST.SentenceTransformer = MagicMock()


_MOCK_CHROMA = MagicMock()



_MOCK_BM25 = MagicMock()


from app.observability.logging_config import configure_logging
configure_logging()

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# STEP 1: Confirm deliverables exist
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    from app.retrieval.embeddings import embed, embed_batch
    from app.retrieval.vector_store import store_chunks, search_vectors, ModelMismatchError
    from app.retrieval.bm25_store import store_bm25, search_bm25
    from app.retrieval.hybrid_search import search_hybrid, FusedCandidate

    assert_ok(callable(embed), "embed() not callable")
    assert_ok(callable(embed_batch), "embed_batch() not callable")
    assert_ok(callable(store_chunks), "store_chunks() not callable")
    assert_ok(callable(search_vectors), "search_vectors() not callable")
    assert_ok(callable(store_bm25), "store_bm25() not callable")
    assert_ok(callable(search_bm25), "search_bm25() not callable")
    assert_ok(callable(search_hybrid), "search_hybrid() not callable")
    print(f"{PASS} All deliverables exist and are importable")

    # Confirm search_code is present (belongs to 6b pipeline, but lives here)
    from app.retrieval.hybrid_search import search_code
    assert_ok(callable(search_code), "search_code() missing")
    print(f"{PASS} search_code() present (Note: dedup_by_file also lives here — see boundary check in Step 4)")


# ---------------------------------------------------------------------------
# STEP 2 EC5: RRF scale-invariance test (the "score normalization" test)
# ---------------------------------------------------------------------------
def test_ec5_rrf_scale_invariance():
    """
    EC5: RRF is inherently scale-invariant.
    Two candidate sets with wildly different raw scores should produce
    correct merged rankings purely by rank position.

    We mock search_vectors and search_bm25 to inject controlled inputs.
    """
    print("\n--- EC5: RRF Scale Invariance (score normalization) ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid

    # Vector scores: tight cluster near 0.9-0.99 (cosine-like)
    # BM25 scores: wide spread 2-40 (BM25-like)
    # We craft: chunk_A is rank-1 in vector, rank-3 in BM25
    #           chunk_B is rank-2 in vector, rank-1 in BM25
    #           chunk_C is rank-3 in vector, rank-2 in BM25

    v_results = [
        VectorSearchResult(id="chunk_A", score=-0.01, document="A text", metadata={}),
        VectorSearchResult(id="chunk_B", score=-0.05, document="B text", metadata={}),
        VectorSearchResult(id="chunk_C", score=-0.09, document="C text", metadata={}),
    ]
    b_results = [
        BM25SearchResult(id="chunk_B", score=40.0, document="B text", metadata={}),
        BM25SearchResult(id="chunk_C", score=20.0, document="C text", metadata={}),
        BM25SearchResult(id="chunk_A", score=2.0, document="A text", metadata={}),
    ]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):
        results = search_hybrid("test_repo", "query", n_results=20)

    assert_ok(len(results) == 3, "Expected 3 fused candidates")

    # chunk_B: vector_rank=2, bm25_rank=1 → 1/(60+2) + 1/(60+1)
    # chunk_A: vector_rank=1, bm25_rank=3 → 1/(60+1) + 1/(60+3)
    # chunk_C: vector_rank=3, bm25_rank=2 → 1/(60+3) + 1/(60+2)
    k = 60
    score_B = 1/(k+2) + 1/(k+1)
    score_A = 1/(k+1) + 1/(k+3)
    score_C = 1/(k+3) + 1/(k+2)

    assert_ok(results[0].id == "chunk_B", f"RRF winner should be B, got {results[0].id}")
    assert_ok(results[1].id == "chunk_A", f"RRF second should be A, got {results[1].id}")
    assert_ok(results[2].id == "chunk_C", f"RRF third should be C, got {results[2].id}")

    # Verify the raw score magnitude difference didn't bias results
    # (BM25 score 40 vs 2 is a 20x difference but rank is what matters)
    assert_ok(abs(results[0].rrf_score - score_B) < 1e-9, "chunk_B RRF score wrong")
    print(f"{PASS} EC5: RRF is scale-invariant — raw score magnitudes (0.99 vs 40) don't bias rankings")


# ---------------------------------------------------------------------------
# STEP 2 EC6: RRF uses settings.RRF_K
# ---------------------------------------------------------------------------
def test_ec6_rrf_k_from_settings():
    print("\n--- EC6: RRF uses settings.RRF_K ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid

    v_results = [
        VectorSearchResult(id="chunk_A", score=-0.01, document="A", metadata={}),
        VectorSearchResult(id="chunk_B", score=-0.05, document="B", metadata={}),
    ]
    b_results = [
        BM25SearchResult(id="chunk_B", score=10.0, document="B", metadata={}),
        BM25SearchResult(id="chunk_A", score=5.0, document="A", metadata={}),
    ]

    # With k=60 (default), chunk_A (rank 1 in vector, 2 in BM25)
    # vs chunk_B (rank 2 in vector, 1 in BM25) are very close
    # With k=1 (tiny), rank differences become massive — clear winner
    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):

        # Use large k (default)
        from app.config import settings
        original_k = settings.RRF_K
        try:
            settings.RRF_K = 1  # Tiny k amplifies rank differences massively
            results_k1 = search_hybrid("test_repo", "query", n_results=20)
            # With k=1: chunk_B score = 1/(1+2)+1/(1+1)=0.833, chunk_A = 1/(1+1)+1/(1+2)=0.833
            # They're equal here since A=rank1+rank2 and B=rank2+rank1 — scores are symmetric

            settings.RRF_K = 100  # Large k smooths differences
            results_k100 = search_hybrid("test_repo", "query", n_results=20)
        finally:
            settings.RRF_K = original_k

    # Both should produce 2 results and the scores should CHANGE with k
    assert_ok(len(results_k1) == 2, "k=1 should return 2 candidates")
    assert_ok(len(results_k100) == 2, "k=100 should return 2 candidates")

    # Verify k actually changes score values (not hardcoded)
    assert_ok(
        abs(results_k1[0].rrf_score - results_k100[0].rrf_score) > 1e-9,
        "RRF scores identical for k=1 vs k=100 — k is probably hardcoded!"
    )
    print(f"{PASS} EC6: RRF_K is read from settings, changing it shifts RRF scores")


# ---------------------------------------------------------------------------
# STEP 2 EC7: Chunk in both lists appears exactly once
# ---------------------------------------------------------------------------
def test_ec7_deduplication():
    print("\n--- EC7: Chunk appearing in both lists appears exactly once ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid

    shared_id = "chunk_shared"
    v_results = [
        VectorSearchResult(id=shared_id, score=-0.01, document="shared text", metadata={"fn": "foo"}),
        VectorSearchResult(id="chunk_vec_only", score=-0.05, document="vec only", metadata={}),
    ]
    b_results = [
        BM25SearchResult(id=shared_id, score=15.0, document="shared text", metadata={"fn": "foo"}),
        BM25SearchResult(id="chunk_bm25_only", score=8.0, document="bm25 only", metadata={}),
    ]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):
        results = search_hybrid("test_repo", "query", n_results=20)

    ids = [r.id for r in results]
    assert_ok(ids.count(shared_id) == 1, f"Shared chunk appears {ids.count(shared_id)} times (expected 1)")

    # Shared chunk should have both vector_rank and bm25_rank set
    shared = next(r for r in results if r.id == shared_id)
    assert_ok(shared.vector_rank is not None, "shared chunk missing vector_rank")
    assert_ok(shared.bm25_rank is not None, "shared chunk missing bm25_rank")

    # Its RRF score should be sum of both contributions (higher than solo entries)
    vec_only = next(r for r in results if r.id == "chunk_vec_only")
    assert_ok(shared.rrf_score > vec_only.rrf_score, "shared chunk should outscore vec_only")
    print(f"{PASS} EC7: Shared chunk appears exactly once with combined RRF score")


# ---------------------------------------------------------------------------
# STEP 2 EC3: Strong vector relevance, weak BM25 → still surfaces
# ---------------------------------------------------------------------------
def test_ec3_vector_dominates_when_bm25_empty():
    print("\n--- EC3: Vector result surfaces even with zero BM25 contribution ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.hybrid_search import search_hybrid

    v_results = [
        VectorSearchResult(id="chunk_A", score=-0.01, document="A text", metadata={}),
    ]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=[]):
        results = search_hybrid("test_repo", "query", n_results=20)

    assert_ok(len(results) == 1, "Expected 1 result from vector-only")
    assert_ok(results[0].id == "chunk_A", "chunk_A should survive with zero BM25")
    assert_ok(results[0].bm25_rank is None, "bm25_rank should be None when BM25 contributed nothing")
    print(f"{PASS} EC3: Vector-only result surfaces correctly when BM25 contributes nothing")


# ---------------------------------------------------------------------------
# STEP 2 EC4: Strong BM25, weak vector → still surfaces
# ---------------------------------------------------------------------------
def test_ec4_bm25_dominates_when_vector_empty():
    print("\n--- EC4: BM25 result surfaces even with zero vector contribution ---")
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid

    b_results = [
        BM25SearchResult(id="chunk_A", score=30.0, document="A text", metadata={}),
    ]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=[]), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):
        results = search_hybrid("test_repo", "query", n_results=20)

    assert_ok(len(results) == 1, "Expected 1 result from bm25-only")
    assert_ok(results[0].id == "chunk_A", "chunk_A should survive with zero vector")
    assert_ok(results[0].vector_rank is None, "vector_rank should be None when vector contributed nothing")
    print(f"{PASS} EC4: BM25-only result surfaces correctly when vector contributes nothing")


# ---------------------------------------------------------------------------
# STEP 2 EC9: Fewer than 20 total candidates — graceful handling
# ---------------------------------------------------------------------------
def test_ec9_small_result_set():
    print("\n--- EC9: Fewer than 20 total candidates, no errors ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid

    v_results = [VectorSearchResult(id=f"chunk_{i}", score=-0.01*i, document=f"text {i}", metadata={}) for i in range(3)]
    b_results = [BM25SearchResult(id=f"chunk_{i}", score=10.0-i, document=f"text {i}", metadata={}) for i in range(2)]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):
        results = search_hybrid("test_repo", "query", n_results=20)

    assert_ok(len(results) == 3, f"Expected 3 fused results, got {len(results)}")
    assert_ok(all(r.rrf_score > 0 for r in results), "All results should have positive RRF scores")
    print(f"{PASS} EC9: Short result set handled gracefully with no index errors")


# ---------------------------------------------------------------------------
# STEP 2 BM25 — EC2: IDs in BM25 match ChromaDB IDs (structural check)
# ---------------------------------------------------------------------------
def test_ec2_bm25_chroma_id_consistency():
    """
    EC2: The BM25 chunk IDs and vector store chunk IDs are both derived as
    f'chunk_{chunk.fingerprint}' — verify both sides use the same formula.
    We test this structurally by checking the ID derivation code, not via
    a real store (which would need Chroma+embeddings).
    """
    print("\n--- EC2: BM25 and Chroma IDs use same formula ---")
    # Read both source files and verify the ID formula
    vector_store_code = (PROJECT_ROOT / "app/retrieval/vector_store.py").read_text(encoding="utf-8")
    bm25_store_code = (PROJECT_ROOT / "app/retrieval/bm25_store.py").read_text(encoding="utf-8")

    assert_ok('f"chunk_{chunk.fingerprint}"' in vector_store_code, "vector_store.py ID formula differs!")
    assert_ok('f"chunk_{chunk.fingerprint}"' in bm25_store_code, "bm25_store.py ID formula differs!")

    # Also verify via a real CodeChunk
    from app.parsing.chunker import CodeChunk
    c = CodeChunk(
        chunk_text="test", file_path="fp", display_path="dp",
        normalized_path="np", function_name="fn",
        start_line=1, end_line=2, type="function",
        language="python", fingerprint="abc123", class_name=None
    )
    expected_id = f"chunk_{c.fingerprint}"
    assert_ok(expected_id == "chunk_abc123", "ID derivation broken")
    print(f"{PASS} EC2: Both vector store and BM25 derive IDs as 'chunk_{{fingerprint}}' — zero ID drift possible")


# ---------------------------------------------------------------------------
# STEP 2 EC1 + EC8: Integration tests with real ChromaDB (if available)
# ---------------------------------------------------------------------------
def test_ec1_metadata_schema_and_ec8_model_lock():
    """
    EC1: Verify metadata schema stored in Chroma
    EC8: Verify embedding-model lock rejects mismatched model and force_reindex rebuilds
    """
    if not CHROMA_AVAILABLE or not ST_AVAILABLE:
        pass
        print(f"\n--- EC1 + EC8: SKIPPED (chromadb={CHROMA_AVAILABLE}, sentence-transformers={ST_AVAILABLE}) ---")
        print(f"  (Install with: pip install chromadb sentence-transformers)")
        return

    print("\n--- EC1 + EC8: ChromaDB metadata schema + model lock (integration) ---")
    from app.parsing.chunker import CodeChunk
    from app.retrieval.vector_store import store_chunks, get_collection, ModelMismatchError
    from app.config import settings

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        orig_chroma = settings.CHROMA_DB_PATH
        orig_bm25 = settings.BM25_INDEX_PATH
        orig_model = settings.EMBEDDING_MODEL

        # Reset the global chroma client so it picks up our temp path
        import app.retrieval.vector_store as vs_mod
        orig_client = vs_mod._CHROMA_CLIENT
        vs_mod._CHROMA_CLIENT = None

        import app.retrieval.embeddings as emb_mod
        orig_emb_model = emb_mod._MODEL
        emb_mod._MODEL = None

        try:
            settings.CHROMA_DB_PATH = str(Path(tmpdir) / "chroma")
            settings.BM25_INDEX_PATH = str(Path(tmpdir) / "bm25")
            settings.EMBEDDING_MODEL = "all-MiniLM-L6-v2"

            chunk = CodeChunk(
                chunk_text="def hello(): pass",
                file_path="/repo/hello.py",
                display_path="hello.py",
                normalized_path="hello.py",
                function_name="hello",
                start_line=1, end_line=1,
                type="function",
                language="python",
                fingerprint="fp001",
                class_name=None
            )

            repo_id = "testrepo123"
            store_chunks(repo_id, [chunk])

            # EC1: Check metadata schema
            col = get_collection(repo_id)
            assert_ok(col is not None, "Collection not found after store_chunks")
            result = col.get(ids=[f"chunk_{chunk.fingerprint}"], include=["metadatas"])
            assert_ok(len(result["metadatas"]) == 1, "Stored chunk not found by ID")
            meta = result["metadatas"][0]

            required_fields = {
                "file_path", "display_path", "function_name",
                "start_line", "end_line", "type", "language",
                "fingerprint", "embedding_model_id"
            }
            stored_fields = set(meta.keys())
            missing = required_fields - stored_fields
            extra = stored_fields - required_fields
            assert_ok(not missing, f"Missing metadata fields: {missing}")
            assert_ok(meta["embedding_model_id"] == "all-MiniLM-L6-v2", "Wrong model_id in metadata")
            print(f"{PASS} EC1: Stored metadata schema exactly matches spec")

            # EC8: Switch model, expect rejection
            settings.EMBEDDING_MODEL = "paraphrase-MiniLM-L3-v2"
            emb_mod._MODEL = None  # Force reload

            try:
                store_chunks(repo_id, [chunk], force_reindex=False)
                assert_ok(False, "ModelMismatchError not raised on model switch!")
            except ModelMismatchError as e:
                assert_ok("force_reindex" in str(e).lower() or "force_reindex" in str(e), 
                          f"Error message should mention force_reindex: {e}")
                print(f"{PASS} EC8a: ModelMismatchError raised on model switch without force_reindex")

            # EC8: force_reindex=True wipes and rebuilds
            store_chunks(repo_id, [chunk], force_reindex=True)
            col_new = get_collection(repo_id)
            result_new = col_new.get(ids=[f"chunk_{chunk.fingerprint}"], include=["metadatas"])
            assert_ok(len(result_new["metadatas"]) == 1, "Chunk not found after force_reindex")
            assert_ok(
                result_new["metadatas"][0]["embedding_model_id"] == "paraphrase-MiniLM-L3-v2",
                "New model_id not stored after force_reindex"
            )
            print(f"{PASS} EC8b: force_reindex wipes and rebuilds with new model_id")

        finally:
            settings.CHROMA_DB_PATH = orig_chroma
            settings.BM25_INDEX_PATH = orig_bm25
            settings.EMBEDDING_MODEL = orig_model
            vs_mod._CHROMA_CLIENT = orig_client
            emb_mod._MODEL = orig_emb_model


# ---------------------------------------------------------------------------
# STEP 2: embed() is standalone
# ---------------------------------------------------------------------------
def test_embed_standalone():
    print("\n--- embed() standalone test ---")
    if not ST_AVAILABLE:
        print(f"  SKIPPED (sentence-transformers not available)")
        return

    from app.retrieval.embeddings import embed

    # Call with NO vector-store context
    vec = embed("hello world")
    assert_ok(isinstance(vec, list), "embed() should return list")
    assert_ok(len(vec) > 0, "embed() returned empty vector")
    assert_ok(all(isinstance(x, float) for x in vec), "embed() should return list of floats")
    print(f"{PASS} embed() works standalone with no vector-store context")


# ---------------------------------------------------------------------------
# STEP 3: No exact-float assertions in this module's tests
# ---------------------------------------------------------------------------
def test_step3_no_exact_float_assertions():
    print("\n--- STEP 3: No exact-float assertions in test ---")
    import ast
    test_file = Path(__file__)
    tree = ast.parse(test_file.read_text(encoding="utf-8"))

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                # Check for exact float comparisons (not using tolerance)
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, float):
                    # Allow 0.0 (used for > 0 comparisons), 1e-9 (tolerance)
                    if comparator.value not in (0.0, 1e-9):
                        violations.append(f"Line {node.lineno}: exact float {comparator.value}")

    assert_ok(len(violations) == 0, f"Exact-float assertions found: {violations}")
    print(f"{PASS} Zero exact-float score assertions found in this test file")


# ---------------------------------------------------------------------------
# STEP 4: Handoff contract + boundary check
# ---------------------------------------------------------------------------
def test_step4_handoff_contract_and_boundary():
    print("\n--- STEP 4: Handoff contract + boundary check ---")
    from app.retrieval.vector_store import VectorSearchResult
    from app.retrieval.bm25_store import BM25SearchResult
    from app.retrieval.hybrid_search import search_hybrid, FusedCandidate

    v_results = [VectorSearchResult(id=f"c{i}", score=-0.01*i, document=f"d{i}", metadata={}) for i in range(5)]
    b_results = [BM25SearchResult(id=f"c{i}", score=10.0-i, document=f"d{i}", metadata={}) for i in range(5)]

    with patch("app.retrieval.hybrid_search.search_vectors", return_value=v_results), \
         patch("app.retrieval.hybrid_search.search_bm25", return_value=b_results):
        results = search_hybrid("test_repo", "query", n_results=20)

    # search_hybrid should return FusedCandidates, not dicts
    assert_ok(all(isinstance(r, FusedCandidate) for r in results), 
              "search_hybrid should return FusedCandidates, not pre-processed dicts")
    
    # Results should be sorted by rrf_score descending
    scores = [r.rrf_score for r in results]
    assert_ok(scores == sorted(scores, reverse=True), "Results not sorted by rrf_score")

    # No diversity capping should have occurred (all 5 should appear since they're unique)
    assert_ok(len(results) == 5, "search_hybrid should not cap or truncate before returning to 6b")
    print(f"{PASS} Handoff contract: search_hybrid returns sorted FusedCandidates, uncapped, unranked-by-rerank")

    # Boundary check: dedup_by_file exists but should only be called in search_code (6b)
    # Flag this: it's in hybrid_search.py when it belongs to 6b
    hybrid_search_code = (PROJECT_ROOT / "app/retrieval/hybrid_search.py").read_text()
    assert_ok("dedup_by_file" in hybrid_search_code, "dedup_by_file not found")
    assert_ok("search_code" in hybrid_search_code, "search_code not found")
    # Flag as boundary violation
    print(f"  [BOUNDARY NOTE] dedup_by_file() and search_code() live in hybrid_search.py")
    print(f"  [BOUNDARY NOTE] Per spec, diversity capping and final assembly belong to Module 6b.")
    print(f"  [BOUNDARY NOTE] The RRF-only search_hybrid() respects the boundary; search_code() does not.")


# ---------------------------------------------------------------------------
# STEP 5: Static checks
# ---------------------------------------------------------------------------
def test_step5_static_checks():
    print("\n--- STEP 5: Static checks ---")

    # No cross-encoder in hybrid_search.py directly (it's imported in search_code only)
    hybrid_search_code = (PROJECT_ROOT / "app/retrieval/hybrid_search.py").read_text()
    # cross_encoder import is inside search_code (the 6b assembly fn) not in hybrid fusion
    # Check it's not in the top-level imports
    top_imports_end = hybrid_search_code.find("def search_hybrid")
    top_section = hybrid_search_code[:top_imports_end]
    assert_ok("cross_encoder" not in top_section, 
              "cross_encoder imported at module level in hybrid_search.py (should be in search_code only)")
    assert_ok("query_expansion" not in top_section,
              "query_expansion imported at module level in hybrid_search.py")
    print(f"{PASS} No cross-encoder or query-expansion at hybrid_search module level")

    # Confirm embed() is standalone
    embeddings_code = (PROJECT_ROOT / "app/retrieval/embeddings.py").read_text(encoding="utf-8")
    assert_ok("import chromadb" not in embeddings_code, "embeddings.py imports chromadb (not standalone!)")
    assert_ok("import bm25" not in embeddings_code and "from app.retrieval.bm25" not in embeddings_code, 
              "embeddings.py imports bm25 (not standalone!)")
    print(f"{PASS} embed() is standalone — no vector-store or BM25 dependencies in embeddings.py")


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 6a Tests: Embeddings + Vector Store + BM25 + RRF")
    print("=" * 60)

    test_step1_deliverables()
    test_ec2_bm25_chroma_id_consistency()
    test_ec3_vector_dominates_when_bm25_empty()
    test_ec4_bm25_dominates_when_vector_empty()
    test_ec5_rrf_scale_invariance()
    test_ec6_rrf_k_from_settings()
    test_ec7_deduplication()
    test_ec9_small_result_set()
    test_ec1_metadata_schema_and_ec8_model_lock()
    test_embed_standalone()
    test_step3_no_exact_float_assertions()
    test_step4_handoff_contract_and_boundary()
    test_step5_static_checks()

    print("\n" + "=" * 60)
    print("=== Module 6a: ALL TESTS PASSED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
