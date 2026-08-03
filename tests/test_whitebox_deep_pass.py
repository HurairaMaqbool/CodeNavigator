# Copyright (c) 2026 Huraira Maqbool
# Deep Whitebox Pass: SSRF, OAuth Expiry/Replay, Partial Ingestion Recovery, Quota Concurrency, Loop Hangs.

import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# 1. Security: SSRF Protection in URL Validation
# ---------------------------------------------------------------------------
from app.ingestion.clone import _validate_url, clone_repo, InvalidURLError

def test_whitebox_ssrf_internal_ips_rejected():
    internal_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:5432",
        "http://127.0.0.1:8000",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/router",
        "https://evil-host.com/user/repo",
    ]
    for url in internal_urls:
        with pytest.raises(InvalidURLError):
            _validate_url(url)

def test_whitebox_ssrf_userinfo_bypass_rejected():
    with pytest.raises(InvalidURLError):
        _validate_url("https://github.com@169.254.169.254/user/repo")


# ---------------------------------------------------------------------------
# 2. Security: Auth Token Expiry & OAuth State Replay
# ---------------------------------------------------------------------------
from app.auth.oidc import create_session_token, decode_session_token, exchange_code
from app.auth.oauth_state import create_state, consume_state

def test_whitebox_auth_session_token_expired():
    user = {"sub": "user_123", "email": "test@example.com", "org_id": "org_test"}
    with patch("app.config.settings.SESSION_TTL_SECONDS", -10):  # Already expired
        token = create_session_token(user)
        decoded = decode_session_token(token)
        assert decoded is None  # Rejected due to expired signature

def test_whitebox_oauth_state_replay_rejected():
    state = create_state()
    assert consume_state(state) is True   # First consume succeeds
    assert consume_state(state) is False  # Replay attempt fails!


# ---------------------------------------------------------------------------
# 3. Data Integrity: Partial-Ingestion Crash Recovery
# ---------------------------------------------------------------------------
from app.ingestion.pipeline import run_ingestion_sync
from app.retrieval.vector_store import get_collection, store_chunks
from app.parsing.chunker import CodeChunk

def test_whitebox_partial_ingestion_recovery(tmp_path):
    repo_id = "test_partial_crash_repo"
    
    chunk = CodeChunk(
        chunk_text="def hello(): pass",
        file_path="src/main.py",
        display_path="src/main.py",
        normalized_path="src/main.py",
        function_name="hello",
        start_line=1,
        end_line=5,
        type="function",
        language="python",
        fingerprint="fp12345",
        class_name=None,
    )
    
    # Simulate first vector store write
    with patch("app.config.settings.CHROMA_DB_PATH", str(tmp_path / "chroma")):
        store_chunks(repo_id, [chunk], force_reindex=True)
        col = get_collection(repo_id)
        assert col is not None and col.count() == 1
        
        # Simulate re-ingestion with force_reindex=True
        store_chunks(repo_id, [chunk], force_reindex=True)
        col2 = get_collection(repo_id)
        assert col2.count() == 1  # Wiped and rebuilt cleanly without duplicating or orphaned state!


# ---------------------------------------------------------------------------
# 4. Quota: Concurrent Quota Check Race Condition
# ---------------------------------------------------------------------------
from app.platform.usage_meter import check_quota, increment, check_and_increment_quota
import concurrent.futures

def test_whitebox_quota_race_condition(tmp_path):
    with patch("app.platform.usage_meter._METER_PATH", tmp_path / "usage_meter.json"):
        with patch("app.platform.usage_meter._use_pg", return_value=False):
            with patch("app.config.settings.ENVIRONMENT", "production"):
                with patch("app.config.settings.QUOTA_CHAT_PER_MONTH", 2):
                    increment("org_race", "chat", 1)  # 1 slot remaining
                    
                    results = []
                    def _worker():
                        return check_and_increment_quota("org_race", "chat")
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(_worker) for _ in range(5)]
                        results = [f.result() for f in futures]
                    
                    # Exactly 1 thread succeeds; the other 4 are blocked
                    assert results.count(True) == 1
                    assert results.count(False) == 4


# ---------------------------------------------------------------------------
# 5. Core Logic: Agent Loop Provider Unreachable Graceful Timeout
# ---------------------------------------------------------------------------
from app.agent.loop import AgentContext, AgentState, _apply_provider_failure

def test_whitebox_agent_loop_unreachable_provider():
    ctx = AgentContext(repo_id="test_repo", question="How does auth work?")
    exc = TimeoutError("Connection to Groq timed out after 20.0s")
    
    msg = _apply_provider_failure(ctx, exc, phase="FINALIZE")
    assert ctx.groq_failed is True
    assert ctx.timed_out is True
    assert "too slow" in msg.lower()
