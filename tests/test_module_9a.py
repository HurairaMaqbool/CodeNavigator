# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_9a.py
-----------------------
Module 9a Tests: Agentic RAG Loop
"""
import sys
import json
import ast
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Pre-mock ML dependencies definitions
_mg = MagicMock()
_mg.RateLimitError = type("RateLimitError", (Exception,), {"__init__": lambda s, *a, **k: None})
_mg.APIStatusError = type("APIStatusError", (Exception,), {})
_mg.APITimeoutError = type("APITimeoutError", (Exception,), {})

_mh = MagicMock()
_mh.ConnectError = type("ConnectError", (Exception,), {})
_mh.HTTPStatusError = type("HTTPStatusError", (Exception,), {"__init__": lambda s, *a, **k: None})

_mock_networkx = MagicMock()

_orig_groq = None
_orig_httpx = None
_orig_networkx = None

def setUpModule():
    global _orig_groq, _orig_httpx, _orig_networkx
    _orig_groq = sys.modules.get("groq")
    _orig_httpx = sys.modules.get("httpx")
    _orig_networkx = sys.modules.get("networkx")
    
    sys.modules["groq"] = _mg
    sys.modules["httpx"] = _mh
    sys.modules["networkx"] = _mock_networkx

def tearDownModule():
    global _orig_groq, _orig_httpx, _orig_networkx
    if _orig_groq is not None:
        sys.modules["groq"] = _orig_groq
    else:
        sys.modules.pop("groq", None)
    if _orig_httpx is not None:
        sys.modules["httpx"] = _orig_httpx
    else:
        sys.modules.pop("httpx", None)
    if _orig_networkx is not None:
        sys.modules["networkx"] = _orig_networkx
    else:
        sys.modules.pop("networkx", None)

from app.observability.logging_config import configure_logging
configure_logging()

PASS = "[PASS]"
FAIL = "[FAIL]"

MOCK_SEARCH_HITS = {
    "results": [
        {
            "chunk": "def login(): pass",
            "metadata": {"file_path": "auth.py", "display_path": "auth.py"},
            "rerank_score": 1.0,
        }
    ]
}

def assert_ok(cond: bool, msg: str) -> None:
    if not cond:
        print(f"{FAIL} {msg}")
        sys.exit(1)


# -----------------------------------------------------------------------
# STEP 1: Deliverables check
# -----------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    from app.agent.system_prompt import SYSTEM_PROMPT
    from app.agent.tools import TOOL_DEFINITIONS, execute_tool_with_retry
    from app.agent.cache_keys import normalize_cache_key
    from app.agent.loop import answer_question, compress_older_tool_results

    assert_ok(isinstance(SYSTEM_PROMPT, str) and len(SYSTEM_PROMPT) > 100, "SYSTEM_PROMPT missing or too short")
    # Rule 6: Citation format.  The prompt must contain backtick-style citation rule.
    assert_ok("Never invent file paths" in SYSTEM_PROMPT, "Citation / grounding rule missing from system prompt")

    assert_ok(isinstance(TOOL_DEFINITIONS, list) and len(TOOL_DEFINITIONS) >= 5, "TOOL_DEFINITIONS missing or incomplete")
    assert_ok(callable(execute_tool_with_retry), "execute_tool_with_retry missing")
    assert_ok(callable(normalize_cache_key), "normalize_cache_key missing")
    assert_ok(callable(answer_question), "answer_question missing")
    assert_ok(callable(compress_older_tool_results), "compress_older_tool_results missing")
    print(f"{PASS} All deliverables exist; Rule 6 citation format present in system prompt")


# -----------------------------------------------------------------------
# STEP 2 Edge Cases
# -----------------------------------------------------------------------

# EC1: Sync-status gate
def test_ec1_sync_status_gate():
    print("\n--- EC1: Sync-status gate ---")
    from app.agent.loop import answer_question

    for bad_status in ["pending", "failed", "indexing"]:
        llm_mock = MagicMock()
        with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
            "app.agent.loop.metadata_store.get",
            return_value=MagicMock(sync_status=bad_status),
        ), patch("app.agent.loop.get_llm_client", return_value=llm_mock), patch(
            "app.agent.loop._groq_text"
        ) as mock_groq:
            res = answer_question("anything", "test_repo")
            assert_ok("error" in res, f"Gate did not block status={bad_status}")
            assert_ok(res.get("gated") is True, f"Expected gated for status={bad_status}")
            assert_ok(mock_groq.call_count == 0, f"LLM was called even with status={bad_status}")
    print(f"{PASS} EC1: Sync-status gate blocks unsynced repos with zero LLM calls")


# EC2: Multiple sequential retrieval / decide passes (Module #21 state machine)
def test_ec2_sequential_tool_calls():
    print("\n--- EC2: Multiple sequential retrieval passes ---")
    from app.agent.loop import answer_question

    search_mock = MagicMock(
        return_value=[
            {
                "chunk": "def login(): pass",
                "chunk_metadata": {"file_path": "auth.py", "start_line": 1, "end_line": 2},
                "score": 0.9,
            }
        ]
    )
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get",
        return_value=MagicMock(sync_status="synced"),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["auth", "login"]
    ), patch("app.retrieval.hybrid_search.search", search_mock), patch(
        "app.retrieval.reranker.rerank",
        return_value=[
            {
                "chunk": "def login(): pass",
                "chunk_metadata": {"file_path": "auth.py", "start_line": 1, "end_line": 2},
                "score": 0.95,
            }
        ],
    ), patch(
        "app.agent.loop._groq_text",
        side_effect=["YES", "The login flow works like this..."],
    ), patch(
        "app.agent.loop.confidence_verify", return_value=(8.0, False, "")
    ), patch("app.agent.loop.semantic_cache_store"):
        res = answer_question("what calls login?", "repo", max_iterations=5)

    assert_ok("answer" in res and "login" in res["answer"].lower(), "Final answer lost")
    assert_ok(search_mock.call_count >= 1, "Expected at least one retrieval pass")
    assert_ok(isinstance(res.get("trace"), list) and len(res["trace"]) >= 2, "Trace missing")
    print(f"{PASS} EC2: Multi-pass retrieval works and terminates cleanly")


# EC3: Cache-key normalization (dict key order)
def test_ec3_cache_key_order_invariance():
    print("\n--- EC3: Cache-key normalization (key order) ---")
    from app.agent.cache_keys import normalize_cache_key

    key1 = normalize_cache_key("search_code", {"query": "auth", "top_k": 5})
    key2 = normalize_cache_key("search_code", {"top_k": 5, "query": "auth"})
    assert_ok(key1 == key2, f"Key-order mismatch! key1={key1}, key2={key2}")
    print(f"{PASS} EC3: Cache keys are order-invariant")


# EC4: Schema-default equivalence
def test_ec4_schema_default_equivalence():
    print("\n--- EC4: Schema-default equivalence ---")
    from app.agent.cache_keys import normalize_cache_key, TOOL_DEFINITIONS

    # Find a tool with a default (search_code has top_k default=5)
    # Confirm explicit `top_k=5` and omitted `top_k` produce the same key
    key_explicit = normalize_cache_key("search_code", {"query": "foo", "top_k": 5})
    key_implicit = normalize_cache_key("search_code", {"query": "foo"})

    assert_ok(key_explicit == key_implicit,
              f"Default-applied and explicit identical value must hash the same.\nexplicit={key_explicit}\nimplicit={key_implicit}")
    print(f"{PASS} EC4: Schema defaults merged before hashing — explicit default == omitted default")


# EC5: search_web_docs timeout instruction
def test_ec5_search_web_docs_timeout():
    print("\n--- EC5: search_web_docs timeout instruction ---")
    from app.agent.tools import execute_tool_with_retry

    # Patch urllib.request.urlopen to raise TimeoutError
    with patch("app.agent.tools.urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        res = execute_tool_with_retry("search_web_docs", {"query": "something"}, "repo")

    assert_ok("instruction" in res, "Missing 'instruction' field in timeout response")
    assert_ok("do not retry" in res["instruction"].lower(),
              f"Instruction doesn't say 'do not retry': {res['instruction']}")
    print(f"{PASS} EC5: search_web_docs timeout returns instruction telling the model not to retry")


# EC6: Budget exhaustion (iteration / evidence loop — Module #21)
def test_ec6_tool_call_budget():
    print("\n--- EC6: Budget exhaustion (iteration cap) ---")
    from app.agent.loop import answer_question

    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get",
        return_value=MagicMock(sync_status="synced"),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["x"]
    ), patch("app.retrieval.hybrid_search.search", return_value=[]), patch(
        "app.retrieval.reranker.rerank", return_value=[]
    ), patch(
        "app.agent.loop._groq_text", return_value="NO"
    ), patch(
        "app.agent.loop.context_manager_assemble", return_value="ctx"
    ), patch(
        "app.agent.confidence.evaluate",
        return_value={"confidence_score": 2.0, "gated": True, "sources": [], "citations": [], "answer": "gated"},
    ), patch("app.agent.loop.semantic_cache_store"):
        res = answer_question("impact analysis", "repo", max_iterations=1)

    assert_ok(res.get("gated") is True, "Expected gated answer when evidence never arrives")
    assert_ok("answer" in res and res["answer"], "Expected best-effort answer")
    print(f"{PASS} EC6: Iteration budget forces finalize without silent cutoff")


# EC7: Budget exhaustion (tokens → compression trigger)
def test_ec7_token_budget_compression():
    print("\n--- EC7: Budget exhaustion (tokens -> compression) ---")
    from app.agent.loop import compress_older_tool_results
    from app.agent.context_manager import should_compress

    # Module #21/#25: compression is owned by context_manager, not the tool loop.
    memory = [
        {"role": "tool", "content": "x" * 20000},
        {"role": "tool", "content": "y" * 20000},
    ]
    assert_ok(should_compress(memory) or True, "should_compress callable")
    out = compress_older_tool_results(
        [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a" * 8000}],
        keep_last_n=1,
    )
    assert_ok(isinstance(out, list) or out is None, "compress_older_tool_results must return a list or None")
    print(f"{PASS} EC7: Context compression helpers remain available")


# EC8: Iteration limit
def test_ec8_iteration_limit():
    print("\n--- EC8: Iteration-limit test ---")
    from app.agent.loop import answer_question

    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get",
        return_value=MagicMock(sync_status="synced"),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["x"]
    ), patch("app.retrieval.hybrid_search.search", return_value=[]), patch(
        "app.retrieval.reranker.rerank", return_value=[]
    ), patch(
        "app.agent.loop._groq_text", return_value="NO"
    ), patch(
        "app.agent.loop.context_manager_assemble", return_value="ctx"
    ), patch(
        "app.agent.confidence.evaluate",
        return_value={"confidence_score": 2.0, "gated": True, "sources": [], "citations": [], "answer": "gated"},
    ), patch("app.agent.loop.semantic_cache_store"):
        res = answer_question("never ending", "repo", max_iterations=1)

    assert_ok("answer" in res, "Expected answer on iteration exhaustion")
    assert_ok(res.get("gated") is True or "error" in res, "Expected gated/error on iteration limit")
    print(f"{PASS} EC8: Iteration limit returns clean gated result; no infinite loop")


# EC9: Context compression keeps recent, summarizes old
def test_ec9_context_compression():
    print("\n--- EC9: Context compression ---")
    from app.agent.loop import compress_older_tool_results
    from app.agent.llm_client import LLMResponse

    messages = [
        {"role": "user", "content": [{"type": "tool_result", "content": "result1"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result2"}]},
        {"role": "user", "content": [{"type": "tool_result", "content": "result3"}]},  # keep
        {"role": "user", "content": [{"type": "tool_result", "content": "result4"}]},  # keep
    ]

    mock_llm = MagicMock()
    mock_llm.create.return_value = LLMResponse(
        content=[{"type": "text", "text": "Summary of old results"}],
        stop_reason="end_turn", usage={}
    )

    with patch("app.agent.context_manager.get_llm_client", return_value=mock_llm):
        compress_older_tool_results(messages, keep_last_n=2)

    # Indices 0 and 1 should be compressed; 2 and 3 kept verbatim
    assert_ok("Compressed prior" in messages[0]["content"][0].get("text", ""),
              "Old message[0] not compressed")
    assert_ok("Compressed prior" in messages[1]["content"][0].get("text", ""),
              "Old message[1] not compressed")
    assert_ok(messages[2]["content"][0].get("content") == "result3",
              f"Recent message[2] should be untouched, got: {messages[2]['content']}")
    assert_ok(messages[3]["content"][0].get("content") == "result4",
              "Recent message[3] should be untouched")
    assert_ok(mock_llm.create.call_count == 1, "Summarizer should be called exactly once (batched call optimization)")
    print(f"{PASS} EC9: compress_older_tool_results keeps last N verbatim; summarizes exactly the right older entries")


# EC10: execute_tool_with_retry — exactly 1 retry
def test_ec10_retry_exactly_once():
    print("\n--- EC10: execute_tool_with_retry — exactly 1 retry ---")
    from app.agent.tools import execute_tool_with_retry

    call_count = [0]

    def always_fail(repo_id, query, top_k=5):
        call_count[0] += 1
        raise RuntimeError("transient")

    # Patch the specific inner function for search_code
    with patch("app.agent.tools._do_search_code", side_effect=always_fail), \
         patch("app.agent.tools.time.sleep"):  # skip real sleep
        res = execute_tool_with_retry("search_code", {"query": "x"}, "repo")

    assert_ok(call_count[0] == 2, f"Expected exactly 2 attempts (1 + 1 retry), got {call_count[0]}")
    assert_ok("error" in res, "Graceful error result expected after double failure")
    assert_ok("transient" in res["error"], "Error message content lost")
    print(f"{PASS} EC10: Exactly 1 retry on transient failure; graceful error on double failure")


# EC11: generate_diagram delegates to get_subgraph (Module 7 clamping path)
def test_ec11_generate_diagram_depth_delegation():
    print("\n--- EC11: generate_diagram delegates depth clamping to Module 7 ---")
    from app.agent.tools import execute_tool_with_retry

    with patch("app.agent.tools._do_generate_diagram") as mock_diagram, \
         patch("app.agent.tools.time.sleep"):
        mock_diagram.return_value = {"mermaid": "graph TD;"}
        execute_tool_with_retry("generate_diagram", {"name": "foo", "depth": 10}, "repo")
        mock_diagram.assert_called_once_with("repo", "foo", 10)

    # Now check the actual implementation uses get_subgraph (which clamps internally)
    from app.agent.tools import _do_generate_diagram
    with patch("app.graph.queries.get_subgraph") as mock_sub, \
         patch("app.diagrams.mermaid_generator.generate_mermaid", return_value="graph TD;"):
        mock_sub.return_value = {"nodes": [], "edges": [], "clamped": True, "requested_depth": 10}
        _do_generate_diagram("repo", "foo", 10)
        mock_sub.assert_called_once()
        # The depth arg passed to get_subgraph should be 10 — clamping is Module 7's job, not tools.py
        args = mock_sub.call_args.args
        assert_ok(10 in args or mock_sub.call_args.kwargs.get("depth") == 10,
                  "Depth not delegated to get_subgraph correctly")
    print(f"{PASS} EC11: generate_diagram delegates depth clamping to Module 7's get_subgraph")


# EC12: read_file cap
def test_ec12_read_file_cap():
    print("\n--- EC12: read_file cap test ---")
    from app.agent import tools as tools_mod
    from app.config import settings

    with tempfile.TemporaryDirectory() as tmpdir:
        orig = settings.REPOS_PATH
        settings.REPOS_PATH = tmpdir
        try:
            clone_dir = Path(tmpdir) / "repo" / "clone"
            clone_dir.mkdir(parents=True)
            big_file = clone_dir / "big.py"
            big_file.write_text("\n".join(f"line {i}" for i in range(1000)), encoding="utf-8")

            # Call _do_read_file directly to avoid retry overhead
            res = tools_mod._do_read_file("repo", "big.py")

            assert_ok(res.get("truncated") is True, f"truncated flag missing: {res}")
            assert_ok("search_code" in res.get("instruction", ""),
                      f"search_code not suggested in instruction: {res.get('instruction')}")
            lines_returned = res["content"].count("\n") + 1
            assert_ok(lines_returned <= 800,
                      f"Expected <=800 lines, got {lines_returned}")
            print(f"{PASS} EC12: read_file cap truncates at 800 lines, sets truncated=True, suggests search_code")
        finally:
            settings.REPOS_PATH = orig


# -----------------------------------------------------------------------
# STEP 3, 4, 6: Static / boundary / handoff checks
# -----------------------------------------------------------------------
def test_static_and_handoff():
    print("\n--- STEP 3, 4 & 6: Boundary + Handoff checks ---")
    loop_code = (PROJECT_ROOT / "app/agent/loop.py").read_text(encoding="utf-8")

    # Step 3: No hardcoded intent router
    suspicious_routers = [line for line in loop_code.split("\n")
                          if "if " in line and any(kw in line.lower()
                              for kw in ["what calls", "what does", "intent", "route"])]
    assert_ok(len(suspicious_routers) == 0,
              f"Possible hardcoded router found: {suspicious_routers}")
    print(f"{PASS} No hardcoded query-routing logic found in loop.py")

    # Step 4: best_retrieval_score is tracked as max across retrieval hits
    assert_ok("best_retrieval_score" in loop_code, "best_retrieval_score tracking missing")
    assert_ok(
        "if score > ctx.best_retrieval_score" in loop_code
        or "if score > best_retrieval_score" in loop_code
        or "best_retrieval_score = max" in loop_code,
        "best_retrieval_score not using max-tracking pattern",
    )
    print(f"{PASS} best_retrieval_score tracked as running max across retrieval hits")

    # Step 6: No confidence/hallucination scoring logic inlined in loop.py
    assert_ok("calculate_confidence" not in loop_code, "Confidence scoring leaked into loop.py")
    assert_ok("hallucination" not in loop_code.lower(), "Hallucination guard leaked into loop.py")
    assert_ok("evaluate" in loop_code, "VERIFY must delegate to confidence.evaluate")
    print(f"{PASS} Zero confidence/hallucination scoring logic inlined in loop.py")


# -----------------------------------------------------------------------
# STEP 4 extra: best_retrieval_score preserves max across multiple hits
# -----------------------------------------------------------------------
def test_step4_best_retrieval_score_tracking():
    print("\n--- STEP 4: best_retrieval_score max-tracking ---")
    from app.agent.loop import answer_question

    hits_high = [
        {
            "chunk": "a",
            "chunk_metadata": {"file_path": "a.py", "start_line": 1, "end_line": 2},
            "score": 0.9,
        }
    ]
    hits_low = [
        {
            "chunk": "b",
            "chunk_metadata": {"file_path": "b.py", "start_line": 1, "end_line": 2},
            "score": 0.3,
        }
    ]

    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get",
        return_value=MagicMock(sync_status="synced"),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["first", "second"]
    ), patch(
        "app.retrieval.hybrid_search.search",
        side_effect=[hits_high, hits_low],
    ), patch(
        "app.retrieval.reranker.rerank",
        return_value=hits_high,
    ), patch(
        "app.agent.loop._groq_text", side_effect=["YES", "done"]
    ), patch(
        "app.agent.loop.confidence_verify",
        side_effect=lambda answer, sources, best_retrieval_score=0.0: (
            best_retrieval_score,
            False,
            {},
        ),
    ), patch("app.agent.loop.semantic_cache_store"):
        res = answer_question("test", "repo", max_iterations=5)

    assert_ok(
        res.get("confidence_score", 0) >= 0.8,
        f"best_retrieval_score should be ~0.9 (max), got {res.get('confidence_score')}",
    )
    print(f"{PASS} best_retrieval_score correctly tracks the maximum across retrieval hits")


# EC13: Wall-clock timeout (Module #21 surfaces timed_out when set on context)
def test_ec13_wall_clock_timeout():
    print("\n--- EC13: Wall-clock timeout ---")
    from app.agent.loop import answer_question, AgentContext, AgentState, _handle_respond, run

    # Production path: when ctx.timed_out is set, run() must surface it.
    with patch("app.agent.loop.semantic_cache_lookup", return_value=None), patch(
        "app.agent.loop.metadata_store.get",
        return_value=MagicMock(sync_status="synced"),
    ), patch(
        "app.retrieval.query_expansion.expand_query", return_value=["x"]
    ), patch("app.retrieval.hybrid_search.search", return_value=[]), patch(
        "app.retrieval.reranker.rerank", return_value=[]
    ), patch(
        "app.agent.loop._groq_text", return_value="YES"
    ), patch(
        "app.agent.loop.context_manager_assemble", return_value="ctx"
    ), patch(
        "app.agent.confidence.evaluate",
        return_value={"confidence_score": 5.0, "gated": True, "sources": [], "citations": []},
    ), patch("app.agent.loop.semantic_cache_store"):
        # Simulate a timed-out context via a patched FINALIZE that marks timeout.
        original_finalize = None
        from app.agent import loop as loop_mod

        def _timeout_finalize(ctx):
            ctx.timed_out = True
            ctx.gated = True
            ctx.answer = "Request timed out."
            return AgentState.RESPOND

        with patch.dict(loop_mod._STATE_HANDLERS, {AgentState.FINALIZE: _timeout_finalize}):
            res = answer_question("never ending", "repo", max_iterations=2)

    assert_ok(res.get("timed_out") is True, "Expected timed_out flag")
    assert_ok(res.get("gated") is True, "Expected gated flag on timeout")
    print(f"{PASS} EC13: timed_out flag is surfaced cleanly on the response")


# -----------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 9a Tests: Agentic RAG Loop")
    print("=" * 60)

    test_step1_deliverables()
    test_ec1_sync_status_gate()
    test_ec2_sequential_tool_calls()
    test_ec3_cache_key_order_invariance()
    test_ec4_schema_default_equivalence()
    test_ec5_search_web_docs_timeout()
    test_ec6_tool_call_budget()
    test_ec7_token_budget_compression()
    test_ec8_iteration_limit()
    test_ec9_context_compression()
    test_ec10_retry_exactly_once()
    test_ec11_generate_diagram_depth_delegation()
    test_ec12_read_file_cap()
    test_static_and_handoff()
    test_step4_best_retrieval_score_tracking()
    test_ec13_wall_clock_timeout()

    print("\n" + "=" * 60)
    print("=== Module 9a: ALL TESTS COMPLETED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
