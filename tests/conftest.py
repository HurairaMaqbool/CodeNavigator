# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Shared pytest fixtures — reset global agent state between tests."""
from __future__ import annotations

import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("PYTEST_RUNNING", "1")

# Stub Celery when not installed so ingestion_task imports succeed in unit tests.
import sys
from unittest.mock import MagicMock

if "celery" not in sys.modules:
    try:
        import celery  # noqa: F401
    except ImportError:
        _celery = MagicMock()
        _celery.Celery = MagicMock(return_value=MagicMock())
        sys.modules["celery"] = _celery

# Mock sentence_transformers to allow tests to run without deep dependency issues
if "sentence_transformers" not in sys.modules:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        # Create mock SentenceTransformer for tests with word-based semantic embeddings
        import numpy as np
        import hashlib
        
        # Shared vocabulary across all mock embeddings for consistency
        _MOCK_EMBEDDING_VOCAB = {}
        _MOCK_EMBEDDING_VOCAB_INDEX = [0]  # Use list to allow mutation in nested function
        
        def _get_word_index(word):
            """Get or assign vocabulary index for a word."""
            if word not in _MOCK_EMBEDDING_VOCAB:
                _MOCK_EMBEDDING_VOCAB[word] = _MOCK_EMBEDDING_VOCAB_INDEX[0]
                _MOCK_EMBEDDING_VOCAB_INDEX[0] += 1
            return _MOCK_EMBEDDING_VOCAB[word]
        
        class MockSentenceTransformer:
            def __init__(self, model_name, *args, **kwargs):
                self.model_name = model_name
            
            def _text_to_embedding(self, text):
                """Convert text to embedding based on word presence in vocabulary."""
                # Normalize text
                text_lower = text.lower()
                words = text_lower.split()
                
                # Build embedding from word indices
                embedding = np.zeros(384, dtype=np.float32)
                
                for word in set(words):
                    word_idx = _get_word_index(word)
                    # Use word index to seed position in embedding space
                    embedding_pos = word_idx % 384
                    # Count occurrences of word in text
                    count = words.count(word)
                    embedding[embedding_pos] += count / (len(words) + 1)
                
                # Add small hash-based noise for uniqueness
                h = hashlib.md5(text_lower.encode()).digest()
                seed = int.from_bytes(h[:4], 'little')
                rng = np.random.RandomState(seed)
                noise = rng.randn(384).astype(np.float32) * 0.05
                embedding += noise
                
                # Normalize to unit length
                norm = np.linalg.norm(embedding)
                if norm > 1e-6:
                    embedding = embedding / norm
                
                return embedding.astype(np.float32)
            
            def encode(self, sentences, *args, **kwargs):
                if isinstance(sentences, str):
                    sentences = [sentences]
                # Return consistent embeddings based on text content
                embeddings = np.array([self._text_to_embedding(s) for s in sentences])
                return embeddings.astype(np.float32)
            
            def similarity(self, embeddings1, embeddings2, *args, **kwargs):
                # Cosine similarity: normalized embeddings dot product
                return np.dot(embeddings1, embeddings2.T)
        
        class MockCrossEncoder:
            def __init__(self, model_name, *args, **kwargs):
                self.model_name = model_name
            
            def predict(self, pairs, *args, show_progress_bar=False, **kwargs):
                """Predict relevance scores for query-document pairs."""
                import numpy as np
                # Return relevance scores in range [0-5] based on text similarity
                # Higher score = more relevant
                scores = []
                for query, doc in pairs:
                    query_lower = query.lower()
                    doc_lower = doc.lower()
                    
                    # Check for exact substring match (very high relevance)
                    if query_lower in doc_lower:
                        score = 4.5
                    else:
                        # Word overlap heuristic
                        query_words = set(query_lower.split())
                        doc_words = set(doc_lower.split())
                        overlap = len(query_words & doc_words)
                        
                        # Check for function/class name match in metadata-like patterns
                        query_name = query_lower.replace(" ", "_")
                        if query_name in doc_lower or f"def {query_name}" in doc_lower or f"class {query_name}" in doc_lower:
                            score = 4.0
                        else:
                            # Base score on word overlap
                            score = min(3.0, overlap * 0.3)
                    
                    scores.append(score)
                return np.array(scores, dtype=np.float32)
        
        _st = MagicMock()
        _st.SentenceTransformer = MockSentenceTransformer
        _st.CrossEncoder = MockCrossEncoder
        _st.util = MagicMock()
        _st.util.pytorch_cos_sim = lambda a, b: MagicMock()
        sys.modules["sentence_transformers"] = _st

import pytest


@pytest.fixture(autouse=True)
def _redis_ping_for_ingest_dispatch(monkeypatch):
    """Ingest uses Celery when Redis is up; tests mock delay and expect that path."""
    monkeypatch.setattr("app.redis_client.ping_redis", lambda: True)
    monkeypatch.setattr("app.api.router._celery_workers_available", lambda: True)


@pytest.fixture(autouse=True)
def _legacy_synced_meta_progress_counts(monkeypatch):
    """Unit tests often use MagicMock(sync_status='synced') without integer counts."""
    import app.ingestion.progress_counts as pc

    original = pc.ingest_progress_counts

    def _wrapped(meta, asset_repo_id, *, job_id=None):
        files, chunks = original(meta, asset_repo_id, job_id=job_id)
        if files > 0 and chunks > 0:
            return files, chunks
        if meta is not None and getattr(meta, "sync_status", None) == "synced":
            fp = getattr(meta, "files_parsed", None)
            cc = getattr(meta, "chunks_created", None)
            if not isinstance(fp, int) and not isinstance(cc, int):
                return 1, 1
        return files, chunks

    monkeypatch.setattr(pc, "ingest_progress_counts", _wrapped)


@pytest.fixture(autouse=True)
def _unlimited_quotas_in_tests(monkeypatch):
    """Tests must not hit real plan quotas (free tier = 5 ingest/mo)."""
    from app.config import settings

    monkeypatch.setattr(settings, "QUOTA_CHAT_PER_MONTH", 0)
    monkeypatch.setattr(settings, "QUOTA_INGEST_PER_MONTH", 0)
    monkeypatch.setattr(settings, "QUOTA_EVAL_PER_MONTH", 0)
    monkeypatch.setattr("app.platform.usage_meter.quota_for_plan", lambda *_a, **_k: 0)


@pytest.fixture(autouse=True)
def _clear_rate_limit_storage():
    """Reset slowapi counters so /ingest tests do not 429 each other."""
    from app.api.rate_limiter import limiter

    def _wipe() -> None:
        try:
            limiter._storage.storage.clear()
        except Exception:
            pass

    _wipe()
    yield
    _wipe()


@pytest.fixture(autouse=True)
def _clear_agent_tool_cache():
    from app.agent.loop import _TOOL_CACHE

    _TOOL_CACHE.clear()
    yield
    _TOOL_CACHE.clear()


@pytest.fixture(autouse=True)
def _clear_expansion_cache():
    import app.retrieval.query_expansion as qe_mod

    qe_mod._EXPANSION_CACHE.clear()
    yield
    qe_mod._EXPANSION_CACHE.clear()


@pytest.fixture(autouse=True)
def _enable_query_expansion_for_tests(monkeypatch):
    """Tests assume expansion can run; .env sets QUERY_EXPANSION_ENABLED=false."""
    from app.config import settings

    monkeypatch.setattr(settings, "QUERY_EXPANSION_ENABLED", True)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Isolated Chroma path for semantic-cache integration tests."""
    from app.config import settings

    chroma_path = tmp_path / "chroma"
    chroma_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "CHROMA_DB_PATH", str(chroma_path))
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    monkeypatch.setattr(settings, "CACHE_SIMILARITY_THRESHOLD", 0.95)
    monkeypatch.setattr(settings, "SEMANTIC_CACHE_ENABLED", True)
    return str(chroma_path)


@pytest.fixture
def mock_api_key():
    """Override API key auth with default-org context for integration tests."""
    from app.api.auth import verify_api_key
    from app.main import app
    from app.platform.api_keys import ApiKeyContext
    from app.platform.tenant_context import set_tenant

    ctx = ApiKeyContext(org_id="default", label="test", key_id="test")

    def _override() -> ApiKeyContext:
        set_tenant(ctx.org_id, api_key_label=ctx.label)
        return ctx

    app.dependency_overrides[verify_api_key] = _override
    yield ctx
    app.dependency_overrides.pop(verify_api_key, None)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """Prevent verify_api_key overrides leaking between tests."""
    yield
    try:
        from app.api.auth import verify_api_key
        from app.main import app

        app.dependency_overrides.pop(verify_api_key, None)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _set_default_tenant():
    from app.platform.tenant_context import set_tenant

    set_tenant("default", api_key_label="test")
    yield


@pytest.fixture
def tmp_repos(tmp_path, monkeypatch):
    """Isolated repos path for semantic-cache integration tests."""
    from app.config import settings

    repos_path = tmp_path / "repos"
    repos_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "REPOS_PATH", str(repos_path))
    return str(repos_path)
