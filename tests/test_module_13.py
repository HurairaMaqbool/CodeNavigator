# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_13.py
-----------------------
Module 13 Tests: GitHub Webhook Auto-Reingest
"""
import sys
import json
import hmac
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Patch ML imports before any app imports





from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)

def _sign(payload: bytes) -> str:
    secret = settings.GITHUB_WEBHOOK_SECRET
    hash_val = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={hash_val}"

def run_tests():
    print("=== Module 13: Security Tests ===")
    
    # Setup test secret
    settings.GITHUB_WEBHOOK_SECRET = "super_secret_test_key_123"
    
    valid_payload = {
        "ref": "refs/heads/main",
        "repository": {
            "default_branch": "main",
            "clone_url": "https://github.com/a/b"
        }
    }
    raw_payload = json.dumps(valid_payload).encode("utf-8")
    sig = _sign(raw_payload)

    # 1. Missing-signature test
    res1 = client.post("/webhook/github", data=b"bad json", headers={"X-GitHub-Event": "push"})
    print(f"{PASS if res1.status_code == 401 else FAIL} Security 1: Missing signature -> 401")
    assert_ok(res1.status_code == 401, "Expected 401 on missing signature")

    # 2. Invalid-signature test
    res2 = client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": "sha256=invalid", "X-GitHub-Event": "push"})
    print(f"{PASS if res2.status_code == 401 else FAIL} Security 2: Invalid signature -> 401")
    assert_ok(res2.status_code == 401, "Expected 401 on invalid signature")

    # 3. Constant-time comparison
    code = Path("app/webhook/github_webhook.py").read_text()
    has_compare = "hmac.compare_digest" in code
    has_bad_eq = "== signature_header" in code or "signature_header ==" in code
    print(f"{PASS if has_compare and not has_bad_eq else FAIL} Security 3: Constant-time comparison (hmac.compare_digest) used natively")
    assert_ok(has_compare and not has_bad_eq, "hmac.compare_digest missing or == used")

    # 4. Raw-bytes-before-parsing test
    messy_json = b'{\n  "ref": "refs/heads/main", \n  "repository": {\n    "default_branch": "main",\n    "clone_url": "https://github.com/a/b"\n  }\n}'
    messy_sig = _sign(messy_json)
    
    with patch("app.webhook.github_webhook.trigger_ingest") as mock_trig:
        mock_trig.return_value = MagicMock(job_id="job", status="processing")
        res4 = client.post("/webhook/github", data=messy_json, headers={"X-Hub-Signature-256": messy_sig, "X-GitHub-Event": "push"})
        print(f"{PASS if res4.status_code == 200 else FAIL} Security 4: Raw-bytes validation allows messy formatting")
        assert_ok(res4.status_code == 200, "Raw bytes check failed for messy JSON")

    # 5. Valid signature computed correctly
    with patch("app.webhook.github_webhook.trigger_ingest") as mock_trig:
        mock_trig.return_value = MagicMock(job_id="job", status="processing")
        res5 = client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"})
        print(f"{PASS if res5.status_code == 200 else FAIL} Security 5: Valid signature accepted correctly")
        assert_ok(res5.status_code == 200, "Valid signature rejected")

    print("\n=== Module 13: Business Logic Edge Cases ===")

    # 1. Non-push event
    with patch("app.webhook.github_webhook.trigger_ingest") as mock_trig:
        res_bl1 = client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "pull_request"})
        ignored1 = res_bl1.json().get("status") == "ignored" and mock_trig.call_count == 0
        print(f"{PASS if ignored1 else FAIL} Logic 1: Non-push event ignored cleanly")
        assert_ok(ignored1, "Failed logic 1")

    # 2. Non-default branch
    feat_payload = {
        "ref": "refs/heads/feature",
        "repository": {
            "default_branch": "main",
            "clone_url": "https://github.com/a/b"
        }
    }
    feat_raw = json.dumps(feat_payload).encode("utf-8")
    feat_sig = _sign(feat_raw)
    with patch("app.webhook.github_webhook.trigger_ingest") as mock_trig:
        res_bl2 = client.post("/webhook/github", data=feat_raw, headers={"X-Hub-Signature-256": feat_sig, "X-GitHub-Event": "push"})
        ignored2 = res_bl2.json().get("status") == "ignored" and mock_trig.call_count == 0
        print(f"{PASS if ignored2 else FAIL} Logic 2: Non-default branch push ignored cleanly")
        assert_ok(ignored2, "Failed logic 2")

    # 3. Default branch -> exact orchestration call
    with patch("app.webhook.github_webhook.trigger_ingest") as mock_trig:
        mock_trig.return_value = MagicMock(job_id="test", status="processing")
        res_bl3 = client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"})
        called_exactly = mock_trig.call_count == 1
        print(f"{PASS if called_exactly else FAIL} Logic 3: Default branch push triggers identical orchestrator")
        assert_ok(called_exactly, "Failed logic 3")

    # 4. Duplicate delivery
    with patch("app.api.router.clone_repo") as mock_clone, \
         patch("app.api.router.filter_repo_files") as mock_filter, \
         patch("app.retrieval.vector_store.get_collection") as mock_col, \
         patch("app.api.router.lock_manager.try_acquire") as mock_lock:
        
        mock_clone.return_value = MagicMock(repo_id="repoX", default_branch="main")
        mock_filter.return_value = [MagicMock()]
        mock_col.return_value = None
        
        # First request acquires lock, second fails
        mock_lock.side_effect = [MagicMock(acquired=True), MagicMock(acquired=False)]
        
        with patch("app.api.router._run_ingest_pipeline"):
            client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"})
            res_bl4 = client.post("/webhook/github", data=raw_payload, headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"})
        
        duplicate_caught = res_bl4.json().get("ingest_status") == "already_running"
        print(f"{PASS if duplicate_caught else FAIL} Logic 4: Duplicate rapid delivery blocked by existing lock")
        assert_ok(duplicate_caught, "Failed logic 4")

    # 5. Missing key
    bad_payload = {"ref": "refs/heads/main", "repository": {}} # missing default_branch
    bad_raw = json.dumps(bad_payload).encode("utf-8")
    bad_sig = _sign(bad_raw)
    res_bl5 = client.post("/webhook/github", data=bad_raw, headers={"X-Hub-Signature-256": bad_sig, "X-GitHub-Event": "push"})
    structured_error = res_bl5.status_code == 400 and "detail" in res_bl5.json()
    print(f"{PASS if structured_error else FAIL} Logic 5: Malformed payload yields structured 400, not 500")
    assert_ok(structured_error, "Failed logic 5")

    print("\n=== Module 13: Full-App Coexistence ===")
    health = client.get("/health").status_code == 200
    
    with patch("app.api.router.clone_repo") as mock_clone, \
         patch("app.api.router.filter_repo_files") as mock_filter, \
         patch("app.retrieval.vector_store.get_collection") as mock_col, \
         patch("app.api.router.lock_manager.try_acquire") as mock_lock:
        mock_clone.return_value = MagicMock(repo_id="r", default_branch="main")
        mock_filter.return_value = []
        mock_col.return_value = None
        ingest = client.post("/ingest", json={"repo_url": "u"}).status_code == 200
    
    with patch("app.api.router.metadata_store.get") as mock_meta, \
         patch("app.api.router.run") as mock_ans, \
         patch("app.api.router.get_subgraph") as mock_sub, \
         patch("app.api.router.graph_to_mermaid") as mock_merm:
        mock_meta.return_value = MagicMock(sync_status="synced", commit_hash="123")
        mock_ans.return_value = {}
        chat = client.post("/chat", json={"repo_id": "r", "question": "q"}).status_code == 200
        mock_merm.return_value = {}
        diagram = client.get("/diagram/r?function_name=a").status_code == 200

    eval_run = client.get("/eval/run", headers={"X-API-Key": settings.API_KEY}).status_code == 200
    webhook = client.post("/webhook/github", data=b"", headers={"X-Hub-Signature-256": ""}).status_code == 401

    all_routes = health and ingest and chat and diagram and eval_run and webhook
    print(f"{PASS if all_routes else FAIL} Coexistence: All 6 routes simultaneously reachable")
    assert_ok(all_routes, "Failed coexistence")
    
    print("\nAll tests passed successfully.")

if __name__ == "__main__":
    run_tests()
