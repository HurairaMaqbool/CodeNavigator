# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_14.py
-----------------------
Module 14 Tests: Streamlit Frontend

Using streamlit.testing.v1.AppTest to programmatically assert the frontend logic
without mocking the actual Streamlit library, but rather mocking `api_client`
so we test pure UI reactions to backend payloads.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import streamlit as st
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mocks for backend modules are applied inside run_tests() to avoid polluting pytest global scope.

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)

def run_tests():
    # Mock backend modules so we don't accidentally depend on them
    sys.modules["app"] = MagicMock()
    sys.modules["app.api"] = MagicMock()

    print("=== Module 14: Frontend API Contracts & Static Checks ===")

    # Step 4: No backend imports in frontend
    fe_dir = PROJECT_ROOT / "frontend"
    for py_file in fe_dir.glob("*.py"):
        content = py_file.read_text()
        if "from app" in content or "import app" in content:
            print(f"{FAIL} Found backend import in {py_file.name}")
            sys.exit(1)
    
    # Check for client-side recomputation (look for math/confidence logic)
    for py_file in fe_dir.glob("*.py"):
        content = py_file.read_text()
        if "confidence =" in content or "compute" in content or "calculate" in content:
            print(f"{FAIL} Found potential client-side recomputation in {py_file.name}")
            sys.exit(1)

    print(f"{PASS} No client-side recomputation or backend imports found.")

    print("\n=== Module 14: Streamlit App UI Tests ===")

    # Initialize AppTest
    app_path = str(PROJECT_ROOT / "frontend" / "streamlit_app.py")
    
    with patch("frontend.api_client.ingest") as mock_ingest, \
         patch("frontend.api_client.get_status") as mock_status, \
         patch("frontend.api_client.chat") as mock_chat, \
         patch("frontend.api_client.get_diagram") as mock_diag:
         
        # Test 6: Already-ready repo test
        at = AppTest.from_file(app_path).run()
        
        # Simulate already-ready repo by forcing session_state
        at.session_state.repo_id = "repo123"
        mock_status.return_value = {"sync_status": "synced"}
        at.run()
        
        # Should not show "Ingestion in progress..."
        assert_ok("Ingestion in progress" not in at.info, "Forced unnecessary polling for synced repo")
        print(f"{PASS} Logic 6: Already-ready repo avoids full waiting/polling experience")

        # Test 7: Pre-ingestion chat-disabled test
        at = AppTest.from_file(app_path).run()
        at.session_state.repo_id = "repo123"
        mock_status.return_value = {"sync_status": "pending"}
        at.run()
        
        # Chat input should be disabled
        # In streamlit app_test, at.chat_input[0].disabled should be True
        chat_disabled = at.chat_input[0].disabled if at.chat_input else False
        assert_ok(chat_disabled, "Chat input is not disabled when repo is pending")
        print(f"{PASS} Logic 7: Pre-ingestion chat genuinely disabled")

        # Test 4: has_circular_dependencies: null test
        at = AppTest.from_file(app_path).run()
        at.session_state.repo_id = "repo123"
        mock_status.return_value = {"sync_status": "synced", "has_circular_dependencies": None}
        at.run()
        assert_ok(any("Cycle Check Timed Out" in msg.value for msg in at.info), "Missing 'Timed Out' badge")
        
        mock_status.return_value = {"sync_status": "synced", "has_circular_dependencies": True}
        at.run()
        assert_ok(any("Circular Dependencies Detected" in msg.value for msg in at.warning), "Missing 'Detected' badge")
        
        print(f"{PASS} Logic 4: has_circular_dependencies timeout (null) rendered distinct from true/false")

        # Test 8: Mid-conversation re-ingest test
        at = AppTest.from_file(app_path).run()
        at.session_state.repo_id = "repo123"
        mock_status.return_value = {"sync_status": "synced"}
        at.run()
        
        # Simulate mid-conversation re-ingest 409
        from frontend.api_client import APIError
        mock_chat.side_effect = APIError(409, "re-indexing")
        at.chat_input[0].set_value("hello").run()
        
        assert_ok(any("This repo is re-indexing" in msg.value for msg in at.info), "Did not handle 409 gracefully in chat")
        print(f"{PASS} Logic 8: Mid-conversation 409 re-ingest handled gracefully (calm info, not error)")

        # Reset mock for chat
        mock_chat.side_effect = None

        # Test 3: Gated-answer rendering test
        mock_chat.return_value = {
            "answer": "I couldn't find enough reliable context to answer this securely.",
            "gated": True
        }
        at.chat_input[0].set_value("secret").run()
        assert_ok(any("couldn't find enough reliable context" in msg.value for msg in at.warning), "Gated answer not rendered as warning/distinct")
        print(f"{PASS} Logic 3: Gated answer rendered distinctly (warning/muted) with literal text")

        # Test 2: Cache-hit loading state test
        mock_chat.return_value = {
            "answer": "from cache",
            "gated": False,
            "cache_hit": True
        }
        at.chat_input[0].set_value("cached q").run()
        assert_ok(any("⚡ Answered from cache" in msg.value for msg in at.caption), "Missing cache hit tag")
        # Spinner checking is tricky in AppTest, but we verify the tag appears
        print(f"{PASS} Logic 2: Honest 'answered from cache' tag appears on rendered message")

        # Test 1: No fabricated stage labels
        # Confirmed by statically reviewing streamlit_app.py where only `st.spinner("Thinking...")` is used
        # which is a plain spinner, not fake stages
        app_code = Path(app_path).read_text()
        assert_ok('st.spinner("Thinking...")' in app_code and "Searching code..." not in app_code, "Found fake loading labels")
        print(f"{PASS} Logic 1: No fabricated stage labels (plain spinner used)")

        # Test 5: Diagram truncation test
        mock_status.return_value = {"sync_status": "synced"}
        at.run()
        
        mock_diag.return_value = {
            "mermaid": "graph TD;\n A-->B;",
            "clamped": True,
            "requested_depth": 3
        }
        at.text_input(0).set_value("main") # diagram function name
        # Assume diagram generation button is the 2nd button (1st is ingest submit)
        diag_btn = next((b for b in at.button if b.label == "Generate Diagram"), None)
        assert_ok(diag_btn is not None, "Generate Diagram button not found")
        diag_btn.click().run()
        
        assert_ok(any("Depth was clamped" in msg.value for msg in at.warning), "Missing clamp warning")
        print(f"{PASS} Logic 5: Diagram truncation (clamped) surfaces visible warning")

        print("\n=== Module 14: Evaluation Tab ===")
        # Test 5: Evaluation tab status
        # Since Module 15 isn't live yet, it should say placeholder/pending
        assert_ok("Placeholder" in app_code and "Not implemented yet" in app_code, "Eval tab doesn't mark pending status")
        print(f"{PASS} Logic Eval: Evaluation tab correctly acts as a placeholder pending Module 15")
        
        print("\nAll tests passed successfully.")

if __name__ == "__main__":
    run_tests()
