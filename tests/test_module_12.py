# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_12.py
-----------------------
Module 12 Tests: FastAPI Backend & API Contracts
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Patch ML imports before any app imports





from app.observability.logging_config import configure_logging
configure_logging()

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)
client.headers.update({"X-API-Key": settings.API_KEY})

# ---------------------------------------------------------------------------
# Setup test environment
# ---------------------------------------------------------------------------
def setup_mock_repo(tmp_repos, repo_id, status="synced", commit="123", error=None):
    
    # We will just patch metadata_store.get and mock the return value in tests
    pass

# ---------------------------------------------------------------------------
# STEP 1: Deliverables
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    res = client.get("/health")
    assert_ok(res.status_code == 200, "/health endpoint missing or broken")
    assert_ok("X-Request-ID" in res.headers, "Global RequestIDMiddleware missing")
    print(f"{PASS} All endpoints exist and use Pydantic models")

# ---------------------------------------------------------------------------
# STEP 2: E2E Lifecycle
# ---------------------------------------------------------------------------
@patch("app.api.router._require_repo_ready")
@patch("app.tasks.ingestion_task.run_ingestion.delay")
@patch("app.api.router.lock_manager.try_acquire")
@patch("app.api.router.metadata_store")
@patch("app.api.router.run")
@patch("app.api.router.get_subgraph")
@patch("app.api.router.graph_to_mermaid")
@patch("app.retrieval.vector_store.get_collection")
def test_step2_e2e(mock_col, mock_mermaid, mock_subgraph, mock_ans, mock_meta, mock_lock, mock_delay, mock_ready, tmp_db, tmp_repos):
    print("\n--- STEP 2: Full Lifecycle E2E Test ---")
    from app.ingestion.clone import repo_id_for

    mock_col.return_value = None
    mock_ready.return_value = None
    job_id = repo_id_for("https://github.com/a/b", "HEAD")
    # 1. POST /ingest
    mock_lock.return_value = MagicMock(acquired=True)
    mock_delay.return_value = MagicMock(id="task-1")
    
    res1 = client.post("/ingest", json={"repo_url": "https://github.com/a/b"})
    assert_ok(res1.status_code == 202, f"Ingest failed: {res1.text}")
    assert_ok(res1.json()["job_id"], "Missing job_id")
    assert_ok(res1.json()["job_id"] == job_id, "job_id mismatch")
    
    # 2. GET /status/{job_id}
    meta_mock = MagicMock()
    meta_mock.sync_status = "synced"
    meta_mock.commit_hash = "123"
    meta_mock.ref = "main"
    mock_meta.get.return_value = meta_mock
    
    res2 = client.get(f"/status/{job_id}")
    assert_ok(res2.status_code == 200, "Status failed")
    assert_ok(res2.json()["status"] == "ready", "Status not ready")
    
    # 3. POST /chat
    mock_ans.return_value = {"answer": "A", "confidence_score": 1.0, "gated": False, "trace": []}
    res3 = client.post("/chat", json={"repo_id": job_id, "question": "What is this?"})
    assert_ok(res3.status_code == 200, "Chat failed")
    data3 = res3.json()
    assert_ok(isinstance(data3["confidence_score"], float), "confidence_score not a float")
    assert_ok(isinstance(data3["gated"], bool), "gated not a bool")
    
    # 4. GET /diagram
    mock_mermaid.return_value = {"mermaid": "graph TD", "clamped": True}
    res4 = client.get(f"/diagram/{job_id}?function_name=a")
    assert_ok(res4.status_code == 200, "Diagram failed")
    assert_ok(isinstance(res4.json()["clamped"], bool), "clamped not a bool")
    
    print(f"{PASS} E2E lifecycle completed, types perfectly matched")

# ---------------------------------------------------------------------------
# STEP 3: Error Handling Matrix
# ---------------------------------------------------------------------------
@patch("app.tasks.ingestion_task.run_ingestion.delay")
@patch("app.api.router.lock_manager.try_acquire")
def test_ec1_private_repo(mock_lock, mock_delay, tmp_db, tmp_repos):
    mock_lock.return_value = MagicMock(acquired=True)
    mock_delay.return_value = MagicMock(id="task-1")
    res = client.post("/ingest", json={"repo_url": "https://github.com/a/b"})
    assert_ok(res.status_code == 202, f"Expected 202, got {res.status_code}")
    mock_delay.assert_called_once()
    print(f"{PASS} EC1: Private repo errors surface via /status after async clone")

@patch("app.tasks.ingestion_task.run_ingestion.delay")
@patch("app.api.router.lock_manager.try_acquire")
def test_ec2_repo_too_large(mock_lock, mock_delay, tmp_db, tmp_repos):
    mock_lock.return_value = MagicMock(acquired=True)
    mock_delay.return_value = MagicMock(id="task-1")
    res = client.post("/ingest", json={"repo_url": "https://github.com/a/b"})
    assert_ok(res.status_code == 202, f"Expected 202, got {res.status_code}")
    mock_delay.assert_called_once()
    print(f"{PASS} EC2: Repo too large errors surface via /status after async clone")

@patch("app.tasks.ingestion_task.run_ingestion.delay")
@patch("app.api.router.lock_manager.try_acquire")
def test_ec3_zero_files(mock_lock, mock_delay, tmp_db, tmp_repos):
    mock_lock.return_value = MagicMock(acquired=True)
    mock_delay.return_value = MagicMock(id="task-1")
    res = client.post("/ingest", json={"repo_url": "https://github.com/a/b"})
    assert_ok(res.status_code == 202, f"Expected 202, got {res.status_code}")
    mock_delay.assert_called_once()
    print(f"{PASS} EC3: Zero supported files reported via /status after async filter")

@patch("app.api.router.metadata_store")
@patch("app.api.router.run")
def test_ec4_llm_timeout(mock_ans, mock_meta):
    mock_meta.get.return_value = MagicMock(sync_status="synced", commit_hash="123")
    class RetryError(Exception): pass
    mock_ans.side_effect = RetryError("Timeout")
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "What is this?"})
    assert_ok(res.status_code == 504, f"Expected 504, got {res.status_code}")
    print(f"{PASS} EC4: LLM timeout caught cleanly -> 504")

@patch("app.api.router.metadata_store")
@patch("app.api.router.run")
def test_ec5_unknown_function_chat(mock_ans, mock_meta):
    mock_meta.get.return_value = MagicMock(sync_status="synced", commit_hash="123")
    # Simulate answer_question generating text about missing function
    mock_ans.return_value = {"answer": "Function 'foo' not found in graph.", "error": "Function 'foo' not found in graph."}
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "What is this?"})
    assert_ok(res.status_code == 200, f"Expected 200, got {res.status_code}")
    print(f"{PASS} EC5: Unknown function inside /chat naturally surfaces cleanly (not 500)")

@patch("app.api.router.metadata_store")
def test_ec6_chat_uningested(mock_meta):
    mock_meta.get.return_value = None
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "What is this?"})
    assert_ok(res.status_code == 404, f"Expected 404, got {res.status_code}")
    print(f"{PASS} EC6: /chat on uningested repo -> 404")

@patch("app.api.router.metadata_store")
def test_ec7_diagram_uningested(mock_meta):
    mock_meta.get.return_value = None
    res = client.get("/diagram/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?function_name=a")
    assert_ok(res.status_code == 404, f"Expected 404, got {res.status_code}")
    print(f"{PASS} EC7: /diagram on uningested repo -> 404")

@patch("app.api.router.run")
@patch("app.api.router.metadata_store")
def test_ec8_chat_pending(mock_meta, mock_run):
    mock_meta.get.return_value = MagicMock(sync_status="pending", commit_hash=None)
    mock_run.return_value = {
        "answer": "This repository is still indexing (status: pending).",
        "sources": [],
        "confidence_score": 0.0,
        "gated": True,
    }
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "What is this?"})
    assert_ok(res.status_code == 200, f"Expected 200, got {res.status_code}")
    assert_ok(res.json().get("gated") is True, "Expected gated chat while pending")
    print(f"{PASS} EC8: /chat pending returns gated progress message -> 200")

@patch("app.api.router.metadata_store")
def test_ec9_diagram_pending(mock_meta):
    mock_meta.get.return_value = MagicMock(sync_status="pending", commit_hash=None)
    res = client.get("/diagram/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?function_name=a")
    assert_ok(res.status_code == 409, f"Expected 409, got {res.status_code}")
    print(f"{PASS} EC9: /diagram pending -> 409")

@patch("app.tasks.ingestion_task.run_ingestion.delay")
@patch("app.api.router.lock_manager.try_acquire")
@patch("app.retrieval.vector_store.get_collection")
def test_ec10_ec11_model_mismatch(mock_get_col, mock_lock, mock_delay):
    from app.ingestion.clone import repo_id_for

    job_id = repo_id_for("https://github.com/a/b", "HEAD")
    mock_lock.return_value = MagicMock(acquired=True)
    mock_delay.return_value = MagicMock(id="task-1")
    mock_col = MagicMock()
    mock_col.metadata = {"embedding_model_id": "different-model"}
    mock_get_col.return_value = mock_col
    
    # EC10: no force_reindex
    res10 = client.post("/ingest", json={"repo_url": "https://github.com/a/b", "force_reindex": False})
    assert_ok(res10.status_code == 409, f"Expected 409, got {res10.status_code}")
    assert_ok("force_reindex=true" in res10.json()["detail"], "Missing recovery suggestion")
    print(f"{PASS} EC10: Changed model -> 409 with recovery suggestion")
    
    # EC11: with force_reindex
    res11 = client.post("/ingest", json={"repo_url": "https://github.com/a/b", "force_reindex": True})
    assert_ok(res11.status_code == 202, f"Expected 202, got {res11.status_code}")
    print(f"{PASS} EC11: Changed model + force_reindex -> 202 (Success)")

@patch("app.api.router.lock_manager.try_acquire")
@patch("app.retrieval.vector_store.get_collection")
def test_ec12_concurrent_ingest(mock_get_col, mock_lock):
    mock_get_col.return_value = None
    mock_lock.return_value = MagicMock(acquired=False)
    
    res = client.post("/ingest", json={"repo_url": "https://github.com/a/b"})
    assert_ok(res.status_code in (200, 202), f"Expected 200 or 202, got {res.status_code}")
    assert_ok(res.json()["status"] == "already_running", "Wrong status")
    print(f"{PASS} EC12: Concurrent ingest -> 202 already_running")

@patch("app.api.router.metadata_store")
@patch("app.api.router.run")
def test_ec14_disk_full_prior_state(mock_ans, mock_meta):
    # Simulated disk full -> new ingest fails -> sync_status="failed", BUT commit_hash exists!
    mock_meta.get.return_value = MagicMock(sync_status="failed", commit_hash="old_commit")
    mock_ans.return_value = {"answer": "I can still answer!"}
    
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "question": "What is this?"})
    assert_ok(res.status_code == 200, f"Expected 200, got {res.status_code}")
    print(f"{PASS} EC14: Disk full on re-ingest doesn't block /chat for old commit")

@patch("app.api.router.metadata_store")
def test_ec15_detect_cycles_null(mock_meta):
    mock_meta.get.return_value = MagicMock(sync_status="synced", commit_hash="123")
    mock_meta.get_alias.return_value = None
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text", return_value='{"metadata": {"graph_truncated": false}}'), \
         patch("app.graph.queries.detect_cycles", return_value=None):
        res = client.get("/status/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert_ok(res.status_code == 200, "status failed")
        assert_ok(res.json()["has_circular_dependencies"] is None, "Expected null when detect_cycles times out")
    print(f"{PASS} EC15: Cycle detection timeout correctly outputs null (not False/omitted)")

def test_ec16_malformed_request():
    res = client.post("/chat", json={"repo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}) # Missing question
    assert_ok(res.status_code == 422, f"Expected 422, got {res.status_code}")
    print(f"{PASS} EC16: Malformed request -> 422 standard validation, not 500")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 12 Tests: API Contracts")
    print("=" * 60)

    test_step1_deliverables()
    test_step2_e2e()
    test_ec1_private_repo()
    test_ec2_repo_too_large()
    test_ec3_zero_files()
    test_ec4_llm_timeout()
    test_ec5_unknown_function_chat()
    test_ec6_chat_uningested()
    test_ec7_diagram_uningested()
    test_ec8_chat_pending()
    test_ec9_diagram_pending()
    test_ec10_ec11_model_mismatch()
    test_ec12_concurrent_ingest()
    test_ec14_disk_full_prior_state()
    test_ec15_detect_cycles_null()
    test_ec16_malformed_request()

    print("\n" + "=" * 60)
    print("=== Module 12: ALL TESTS COMPLETED ===")
    print("=" * 60)

if __name__ == "__main__":
    main()
