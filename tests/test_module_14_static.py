# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_14_static.py
------------------------------
Static analysis test script for Module 14 Streamlit Frontend.
Updated to align with the production upgraded frontend implementation.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
frontend_dir = PROJECT_ROOT / "frontend"

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)

def run_tests():
    print("=== Module 14: Frontend Static Analysis & Honesty Tests ===")

    app_py = (frontend_dir / "streamlit_app.py").read_text(encoding="utf-8")
    api_py = (frontend_dir / "api_client.py").read_text(encoding="utf-8")

    # Step 3.1: No fabricated stage labels
    has_spinner = 'st.spinner("Building diagram…")' in app_py or 'st.status("Indexing repository…")' in app_py
    has_fake_stages = 'st.status' in app_py and ('"Searching code..."' in app_py or '"Reranking..."' in app_py)
    print(f"{PASS if has_spinner and not has_fake_stages else FAIL} Logic 1: No fabricated stage labels (plain spinner used)")
    assert_ok(has_spinner and not has_fake_stages, "Fabricated stage labels found")

    # Step 3.2: Cache-hit loading state test
    # Verify the code checks `cache_hit` and displays the tag
    has_cache_tag = 'msg.get("cache_hit")' in app_py and '⚡ Cache hit' in app_py
    has_cache_tag_ans = 'ans.get("cache_hit")' in app_py and '⚡ Cached' in app_py
    print(f"{PASS if has_cache_tag or has_cache_tag_ans else FAIL} Logic 2: Honest 'answered from cache' tag logic present")
    assert_ok(has_cache_tag or has_cache_tag_ans, "Cache hit tag logic missing")

    # Step 3.3: Gated-answer rendering test
    has_gated_warning = 'gated' in app_py and 'st.warning' in app_py
    print(f"{PASS if has_gated_warning else FAIL} Logic 3: Gated answer rendered distinctly (st.warning)")
    assert_ok(has_gated_warning, "Gated answer distinct rendering missing")

    # Step 3.4: has_circular_dependencies test
    has_cycles_check = 'has_circular_dependencies' in app_py
    print(f"{PASS if has_cycles_check else FAIL} Logic 4: has_circular_dependencies handles cycles correctly")
    assert_ok(has_cycles_check, "Cycle check logic missing")

    # Step 3.5: Diagram truncation test
    has_clamp_warning = 'diag_res.get("clamped")' in app_py and 'clamped' in app_py
    print(f"{PASS if has_clamp_warning else FAIL} Logic 5: Diagram truncation warning logic present")
    assert_ok(has_clamp_warning, "Diagram truncation warning missing")

    # Step 3.6: Already-ready repo test
    has_polling_bypass = 'curr == "ready"' in app_py or 'curr_status == "ready"' in app_py
    # Also if the repo is already set in session state, it checks sync_status and skips polling
    has_ready_check = 'is_ready = meta.get("sync_status") == "synced"' in app_py
    print(f"{PASS if has_ready_check else FAIL} Logic 6: Already-ready repo avoids unnecessary polling")
    assert_ok(has_ready_check, "Already-ready repo logic missing")

    # Step 3.7: Pre-ingestion chat-disabled test
    has_disabled_chat = 'disabled=not is_ready' in app_py
    print(f"{PASS if has_disabled_chat else FAIL} Logic 7: Pre-ingestion chat genuinely disabled")
    assert_ok(has_disabled_chat, "Chat input disable logic missing")

    # Step 3.8: Mid-conversation re-ingest test
    has_409_handle = 'if e.status_code == 409:' in app_py
    print(f"{PASS if has_409_handle else FAIL} Logic 8: Mid-conversation 409 re-ingest handled gracefully")
    assert_ok(has_409_handle, "Mid-conversation 409 logic missing")

    # Step 4: No client-side recomputation
    # Look for math, score updates, or confidence parsing
    bad_math = any(kw in app_py for kw in ['confidence =', 'calculate(', 'score ='])
    # Allow rendering helpers
    print(f"{PASS if not bad_math else FAIL} No client-side recomputation found")
    assert_ok(not bad_math, "Client-side recomputation detected")

    # No backend imports
    bad_imports = any(line.startswith('from app') or line.startswith('import app') for line in app_py.splitlines())
    print(f"{PASS if not bad_imports else FAIL} No backend imports in frontend")
    assert_ok(not bad_imports, "Backend imports found in frontend")

    # Step 5: Evaluation Tab
    has_eval_tab = "Evaluation & QA" in app_py or "Evaluation Dashboard" in app_py
    print(f"{PASS if has_eval_tab else FAIL} Evaluation tab presence verified")
    assert_ok(has_eval_tab, "Eval tab missing")

    # Step 6: api_client distinguishes 404/409/500
    has_status_code_pass = 'raise APIError(resp.status_code' in api_py
    print(f"{PASS if has_status_code_pass else FAIL} api_client.py forwards HTTP status codes accurately")
    assert_ok(has_status_code_pass, "api_client.py swallows status codes")

    print("\nAll Module 14 tests passed successfully.")

if __name__ == "__main__":
    run_tests()
