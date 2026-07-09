# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""Shared pytest fixtures — reset global agent state between tests."""
from __future__ import annotations

import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import pytest


@pytest.fixture(autouse=True)
def _redis_ping_for_ingest_dispatch(monkeypatch):
    """Ingest uses Celery when Redis is up; tests mock delay and expect that path."""
    monkeypatch.setattr("app.redis_client.ping_redis", lambda: True)


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
    from app.api.auth import verify_api_key
    from app.main import app

    app.dependency_overrides.pop(verify_api_key, None)


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
