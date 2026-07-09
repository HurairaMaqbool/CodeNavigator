# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_9b.py
-----------------------
Module 9b Tests: Validation, Guard, Confidence, Gating
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.observability.logging_config import configure_logging
configure_logging()

PASS = "[PASS]"
FAIL = "[FAIL]"

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# STEP 1: Deliverables
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    from app.agent.confidence import (
        FILE_PATH_PATTERN, FUNCTION_CALL_PATTERN, 
        extract_file_path_mentions, extract_function_name_mentions,
        validate_and_return, compute_confidence_score
    )
    
    assert_ok(callable(extract_file_path_mentions), "extract_file_path_mentions missing")
    assert_ok(callable(extract_function_name_mentions), "extract_function_name_mentions missing")
    assert_ok(callable(validate_and_return), "validate_and_return missing")
    assert_ok(callable(compute_confidence_score), "compute_confidence_score missing")
    
    print(f"{PASS} All deliverables exist")


# ---------------------------------------------------------------------------
# STEP 2 Edge Cases
# ---------------------------------------------------------------------------

def test_ec1_citation_extraction():
    print("\n--- EC1: Citation extraction precision ---")
    from app.agent.confidence import extract_file_path_mentions
    
    # Text containing file paths with and without line numbers
    text = "It is in `src/auth/login.py:12` and also `src/utils.js:10-15` and `main.py`"
    matches = extract_file_path_mentions(text)
    
    assert_ok("src/auth/login.py" in matches, "Failed to strip line number :12")
    assert_ok("src/utils.js" in matches, "Failed to strip line range :10-15")
    assert_ok("main.py" in matches, "Failed to extract plain file path")
    assert_ok(len(matches) == 3, f"Expected 3 matches, got {len(matches)}: {matches}")
    
    print(f"{PASS} EC1: File paths extracted successfully with line numbers precisely stripped")


def test_ec2_dotted_call_extraction():
    print("\n--- EC2: Dotted-call extraction ---")
    from app.agent.confidence import extract_function_name_mentions
    
    text = "Calls `self.auth.validate_token()` directly."
    matches = extract_function_name_mentions(text)
    
    assert_ok(len(matches) == 1, f"Expected 1 match, got {len(matches)}")
    assert_ok(matches[0] == "validate_token", f"Extracted wrong segment: {matches[0]}")
    
    print(f"{PASS} EC2: Dotted function calls extract only the final function segment correctly")


# Repo metadata mock for EC3-EC9
MOCK_REPO_META = [
    {
        "display_path": "src/auth/login.py",
        "file_path": "src/auth/login.py",
        "normalized_path": "src/auth/login.py",
        "function_name": "validate_token",
        "start_line": 10,
        "end_line": 20
    },
    {
        "display_path": "src/auth/login.py",
        "file_path": "src/auth/login.py",
        "normalized_path": "src/auth/login.py",
        "function_name": "do_login",
        "start_line": 25,
        "end_line": 40
    },
    {
        "display_path": "src/utils.py",
        "file_path": "src/utils.py",
        "normalized_path": "src/utils.py",
        "function_name": None,
        "start_line": 1,
        "end_line": 100
    }
]

def test_ec3_fully_grounded():
    print("\n--- EC3: Fully-grounded answer ---")
    from app.agent.confidence import validate_and_return
    
    ans = [{"type": "text", "text": "Call `validate_token()` in `src/auth/login.py:12`."}]
    
    with patch("app.agent.confidence._load_repo_metadata", return_value=MOCK_REPO_META):
        res = validate_and_return(ans, "repo", [], 0.9)
        
    assert_ok(res.get("invalid_reference_ratio") == 0.0, f"Expected 0.0 ratio, got {res.get('invalid_reference_ratio')}")
    assert_ok(res.get("gated") is False, "Response was incorrectly gated")
    assert_ok("warning" not in res, "Warning field present on perfectly grounded answer")
    
    # Sources check
    sources = res.get("sources", [])
    assert_ok(len(sources) == 1, f"Expected 1 source, got {len(sources)}")
    assert_ok(sources[0]["file_path"] == "src/auth/login.py", "Wrong file path")
    assert_ok(sources[0]["function_name"] == "validate_token", "Wrong function name")
    assert_ok(sources[0]["lines"] == "10-20", "Lines not pulled from real metadata!")
    
    print(f"{PASS} EC3: Fully grounded answer passes completely with correct source metadata construction")


def test_ec4_zero_citation():
    print("\n--- EC4: Zero-citation answer ---")
    from app.agent.confidence import validate_and_return, compute_confidence_score
    
    ans = [{"type": "text", "text": "The login process works by checking tokens."}] # Plausible, zero citations
    
    with patch("app.agent.confidence._load_repo_metadata", return_value=MOCK_REPO_META):
        res = validate_and_return(ans, "repo", [], 0.9)
        
    assert_ok(res.get("invalid_reference_ratio") is None, "Zero citations should yield None ratio, not 0")
    
    # Verify score is measurably lower than grounded
    score_zero = compute_confidence_score(None, 0.9, 0)
    score_grounded = compute_confidence_score(0.0, 0.9, 2)
    assert_ok(score_zero < score_grounded, f"Zero-citation score ({score_zero}) not lower than grounded ({score_grounded})")
    
    print(f"{PASS} EC4: Zero citations returns None ratio and incurs a numeric penalty versus cited answers")


def test_ec5_partially_invalid():
    print("\n--- EC5: Partially-invalid answer ---")
    from app.agent.confidence import validate_and_return
    
    # validate_token is real, fake_function is not
    ans = [{"type": "text", "text": "See `validate_token()` and `fake_function()` in `src/auth/login.py`."}]
    
    with patch("app.agent.confidence._load_repo_metadata", return_value=MOCK_REPO_META):
        res = validate_and_return(ans, "repo", [], 0.9)
        
    assert_ok("warning" in res, "Missing warning field for invalid reference")
    assert_ok("fake_function" in res["warning"], "Warning does not name the invalid function")
    
    sources = res.get("sources", [])
    funcs_in_sources = [s["function_name"] for s in sources]
    assert_ok("validate_token" in funcs_in_sources, "Valid function missing from sources")
    assert_ok("fake_function" not in funcs_in_sources, "Invalid function leaked into sources array!")
    
    print(f"{PASS} EC5: Partially invalid answer warns precisely and filters sources perfectly")


def test_ec6_fully_fabricated():
    print("\n--- EC6: Fully-fabricated answer (Gated) ---")
    from app.agent.confidence import validate_and_return
    from app.config import settings
    
    fabrication = "You should definitely call `totally_fake()` inside `src/does_not_exist.py:44`. THIS IS FAKE."
    ans = [{"type": "text", "text": fabrication}]
    
    with patch("app.agent.confidence._load_repo_metadata", return_value=MOCK_REPO_META):
        res = validate_and_return(ans, "repo", [], 0.1) # Poor retrieval too
        
    assert_ok(res.get("confidence_score", 10) < settings.MIN_CONFIDENCE_SCORE, "Score did not fall below threshold")
    assert_ok(res.get("gated") is True, "Answer was not gated!")
    
    # NO LEAKS CHECK
    ans_text = res.get("answer", "")
    assert_ok("THIS IS FAKE" not in ans_text, "Fabricated text leaked into answer field!")
    assert_ok("could not find enough reliable context" in ans_text.lower(), "Refusal message not applied")

    # Gated responses may include an empty sources list (no retrieval hits in this test)
    assert_ok("sources" in res and res.get("sources") == [], "Expected empty sources on gated response")
    
    # Deep grep the response
    res_str = json.dumps(res)
    assert_ok("THIS IS FAKE" not in res_str, f"Fabricated text leaked SOMEWHERE into response dict! {res_str}")
    
    print(f"{PASS} EC6: Fully fabricated answers are brutally gated with exactly ZERO raw text leaking through")


def test_ec7_none_retrieval_score():
    print("\n--- EC7: None retrieval score ---")
    from app.agent.confidence import compute_confidence_score
    
    # 0 invalid ratio, None retrieval, 2 citations
    score = compute_confidence_score(0.0, None, 2)
    assert_ok(isinstance(score, float), f"Score is not a float: {score}")
    assert_ok(score >= 0.0, "Score crashed or went negative on None retrieval")
    
    print(f"{PASS} EC7: None retrieval score degrades gracefully to 0 without crashing")


def test_ec8_ranking_sanity():
    print("\n--- EC8: Confidence-score ranking sanity ---")
    from app.agent.confidence import compute_confidence_score
    
    s_grounded = compute_confidence_score(0.0, 0.9, 2)
    s_zero = compute_confidence_score(None, 0.9, 0)
    s_partial = compute_confidence_score(0.5, 0.9, 2)
    s_fake = compute_confidence_score(1.0, 0.1, 2)
    
    assert_ok(s_grounded > s_partial, f"Grounded ({s_grounded}) should beat Partial ({s_partial})")
    assert_ok(s_grounded > s_zero, f"Grounded ({s_grounded}) should beat Zero-cited ({s_zero})")
    assert_ok(s_partial > s_fake, f"Partial ({s_partial}) should beat Fake ({s_fake})")
    
    print(f"{PASS} EC8: Score rankings perfectly align with intuitive quality (Grounded > Partial > Fake)")


def test_ec9_gate_boundary():
    print("\n--- EC9: Gate-boundary test ---")
    from app.agent.confidence import validate_and_return
    from app.config import settings
    
    threshold = settings.MIN_CONFIDENCE_SCORE
    assert_ok(threshold > 0, "Threshold is zero, cannot test boundary")
    
    ans = [{"type": "text", "text": "Just some text"}]
    
    # We monkeypatch compute_confidence_score to return EXACTLY threshold, then exactly threshold - 0.1
    with patch("app.agent.confidence._load_repo_metadata", return_value=[]):
        with patch("app.agent.confidence.compute_confidence_score", return_value=threshold):
            res_on = validate_and_return(ans, "repo", [], 0.5)
            assert_ok(res_on.get("gated") is False, "Exactly on threshold should PASS (< check, not <=)")
            
        with patch("app.agent.confidence.compute_confidence_score", return_value=threshold - 0.1):
            res_below = validate_and_return(ans, "repo", [], 0.5)
            assert_ok(res_below.get("gated") is True, "Below threshold should FAIL")
        
    print(f"{PASS} EC9: Gate activates exactly below the threshold (strict < boundary)")


# ---------------------------------------------------------------------------
# STEP 3 & 4: API Contract & Sources
# ---------------------------------------------------------------------------
def test_step3_and_4_contracts():
    print("\n--- STEP 3 & 4: Sources dedup and Contract ---")
    from app.agent.confidence import validate_and_return
    
    # Duplicate mention
    ans = [{"type": "text", "text": "Call `validate_token()` in `src/auth/login.py`. Also, `validate_token()` does things."}]
    
    with patch("app.agent.confidence._load_repo_metadata", return_value=MOCK_REPO_META):
        res = validate_and_return(ans, "repo", [{"trace": "mock"}], 0.9)
        
    sources = res.get("sources", [])
    assert_ok(len(sources) == 1, f"Expected exactly 1 source (deduplicated), got {len(sources)}")
    print(f"{PASS} Sources successfully deduplicate repeated mentions in text")
    
    # Contract Check
    expected_keys = {"answer", "sources", "confidence", "confidence_score", "invalid_reference_ratio", "gated", "trace"}
    actual_keys = set(res.keys())
    
    assert_ok(expected_keys.issubset(actual_keys), f"Missing keys in response! Expected {expected_keys}, got {actual_keys}")
    assert_ok(isinstance(res["gated"], bool), f"gated is not a pure boolean! {type(res['gated'])}")
    print(f"{PASS} Response dictionary perfectly matches Module 12's rigorous API contract")


# ---------------------------------------------------------------------------
# STEP 5: Static Checks
# ---------------------------------------------------------------------------
def test_step5_static_checks():
    print("\n--- STEP 5: Static Boundary Checks ---")
    conf_path = PROJECT_ROOT / "app/agent/confidence.py"
    code = conf_path.read_text(encoding="utf-8")
    
    assert_ok("0.5" in code and "0.35" in code and "0.15" in code, "Confidence score weights maliciously altered!")
    assert_ok("tool_use" not in code and "max_iterations" not in code, "Loop/Tool logic leaked into confidence module!")
    
    print(f"{PASS} Zero loop/caching logic leaked; confidence formula perfectly intact")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 9b Tests: Confidence & Gating")
    print("=" * 60)

    test_step1_deliverables()
    test_ec1_citation_extraction()
    test_ec2_dotted_call_extraction()
    test_ec3_fully_grounded()
    test_ec4_zero_citation()
    test_ec5_partially_invalid()
    test_ec6_fully_fabricated()
    test_ec7_none_retrieval_score()
    test_ec8_ranking_sanity()
    test_ec9_gate_boundary()
    test_step3_and_4_contracts()
    test_step5_static_checks()

    print("\n" + "=" * 60)
    print("=== Module 9b: ALL TESTS COMPLETED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
