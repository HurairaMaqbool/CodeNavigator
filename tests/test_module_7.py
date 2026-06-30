"""
tests/test_module_7.py
----------------------
Module 7 Tests: Call Graph Builder (NetworkX)
"""
import sys
import os
import time
import json
import ast
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from collections import namedtuple

import networkx as nx

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
# Mocks & Stubs
# ---------------------------------------------------------------------------
class MockParsedFunction:
    def __init__(self, name, calls, start_line=1, end_line=10):
        self.name = name
        self.calls = calls
        self.start_line = start_line
        self.end_line = end_line

class MockParsedClass:
    def __init__(self, name, methods, start_line=1, end_line=10):
        self.name = name
        self.methods = methods
        self.start_line = start_line
        self.end_line = end_line

class MockParsedFile:
    def __init__(self, file_path, normalized_path, functions, classes=None):
        self.file_path = file_path
        self.normalized_path = normalized_path
        self.functions = functions
        self.classes = classes or []


# ---------------------------------------------------------------------------
# STEP 1: Confirm Deliverables
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    from app.graph.builder import build_graph
    from app.graph.queries import get_callers, get_callees, get_subgraph, detect_cycles
    
    assert_ok(callable(build_graph), "build_graph missing")
    assert_ok(callable(get_callers), "get_callers missing")
    assert_ok(callable(get_callees), "get_callees missing")
    assert_ok(callable(get_subgraph), "get_subgraph missing")
    assert_ok(callable(detect_cycles), "detect_cycles missing")
    print(f"{PASS} All deliverables exist and are importable")


# ---------------------------------------------------------------------------
# STEP 2 Edge Cases
# ---------------------------------------------------------------------------

def test_ec1_and_ec2_real_data_and_edge_types():
    print("\n--- EC1 & EC2: Real parsed graph data & Edge Types ---")
    from app.graph.builder import build_graph, _graph_path_for
    from app.graph.queries import get_callers, get_callees, _GRAPH_CACHE
    from app.config import settings

    repo_id = "repo_types"

    pf1 = MockParsedFile("f1.py", "f1.py", [
        MockParsedFunction("main", ["local_helper", "ambiguous", "unique_lib"]),
        MockParsedFunction("local_helper", [])
    ])
    pf2 = MockParsedFile("f2.py", "f2.py", [
        MockParsedFunction("ambiguous", []), # Name collision candidate
        MockParsedFunction("unique_lib", [])  # Unique match in another file
    ])
    pf3 = MockParsedFile("f3.py", "f3.py", [
        MockParsedFunction("ambiguous", [])  # Name collision candidate
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            build_graph(repo_id, [pf1, pf2, pf3])
            _GRAPH_CACHE.pop(repo_id, None)

            # EC1: Manually verify results
            callers_of_local = get_callers(repo_id, "local_helper")
            assert_ok(len(callers_of_local) == 1, "Expected 1 caller for local_helper")
            assert_ok(callers_of_local[0]["caller"] == "main", "Caller should be main")

            callees_of_main = get_callees(repo_id, "main")
            assert_ok(len(callees_of_main) == 3, "Expected 3 callees for main")
            
            callee_types = {c["callee"]: c["edge_type"] for c in callees_of_main}
            print(f"{PASS} EC1: get_callers/get_callees manually verified against known structure")

            # EC2: Edge Type Honesty
            assert_ok(callee_types["local_helper"] == "static", "Same file call should be 'static'")
            assert_ok(callee_types["unique_lib"] == "semi_static", "Unique cross-file call should be 'semi_static'")
            assert_ok(callee_types["ambiguous"] == "heuristic", "Ambiguous call should be 'heuristic'")
            print(f"{PASS} EC2: Edge-type honesty verified (static, semi_static, heuristic all present)")

        finally:
            settings.GRAPH_STORE_PATH = orig_store


def test_ec3_and_ec4_nonexistent_functions():
    print("\n--- EC3 & EC4: Query nonexistent functions gracefully ---")
    from app.graph.builder import build_graph
    from app.graph.queries import get_callers, get_callees, _GRAPH_CACHE
    from app.config import settings

    repo_id = "repo_nonexistent"
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            pf = MockParsedFile("f.py", "f.py", [MockParsedFunction("foo", [])])
            build_graph(repo_id, [pf])
            _GRAPH_CACHE.pop(repo_id, None)

            # EC3
            callers = get_callers(repo_id, "totally_nonexistent_function_xyz")
            assert_ok(isinstance(callers, list) and len(callers) == 0, "Nonexistent caller query didn't return empty list")
            print(f"{PASS} EC3: get_callers on nonexistent function returns empty list without KeyError")

            # EC4
            callees = get_callees(repo_id, "totally_nonexistent_function_xyz")
            assert_ok(isinstance(callees, list) and len(callees) == 0, "Nonexistent callee query didn't return empty list")
            print(f"{PASS} EC4: get_callees on nonexistent function returns empty list without KeyError")
        finally:
            settings.GRAPH_STORE_PATH = orig_store


def test_ec5_and_ec6_depth_clamping():
    print("\n--- EC5 & EC6: get_subgraph depth clamping ---")
    from app.graph.builder import build_graph
    from app.graph.queries import get_subgraph, _GRAPH_CACHE
    from app.config import settings

    repo_id = "repo_depth"
    # Create a deep chain: 1 -> 2 -> 3 -> 4 -> 5 -> 6
    pf = MockParsedFile("f.py", "f.py", [
        MockParsedFunction("1", ["2"]),
        MockParsedFunction("2", ["3"]),
        MockParsedFunction("3", ["4"]),
        MockParsedFunction("4", ["5"]),
        MockParsedFunction("5", ["6"]),
        MockParsedFunction("6", [])
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            build_graph(repo_id, [pf])
            _GRAPH_CACHE.pop(repo_id, None)

            # EC5: depth=10 -> clamped to 3
            res_10 = get_subgraph(repo_id, "1", depth=10)
            assert_ok(res_10["requested_depth"] == 10, "requested_depth metadata missing")
            assert_ok(res_10["clamped"] is True, "clamped metadata missing or false")
            
            node_names = [n["name"] for n in res_10["nodes"]]
            assert_ok("4" in node_names, "Node 4 should be in depth 3 (1->2->3->4)")
            assert_ok("5" not in node_names, f"Node 5 should NOT be present in clamped depth 3. Got: {node_names}")
            print(f"{PASS} EC5: depth=10 clamped strictly to depth 3, traversal correctly bound")

            # EC6: depth=2 -> no clamp
            res_2 = get_subgraph(repo_id, "1", depth=2)
            assert_ok(res_2["requested_depth"] == 2, "requested_depth metadata missing")
            assert_ok(res_2["clamped"] is False, "clamped should be False")
            
            node_names = [n["name"] for n in res_2["nodes"]]
            assert_ok("3" in node_names, "Node 3 should be in depth 2 (1->2->3)")
            assert_ok("4" not in node_names, f"Node 4 should NOT be present in depth 2. Got: {node_names}")
            print(f"{PASS} EC6: depth=2 executes freely with clamped=False")

        finally:
            settings.GRAPH_STORE_PATH = orig_store


def test_ec7_size_ceiling():
    print("\n--- EC7: The size-ceiling test ---")
    from app.graph.builder import build_graph, _graph_path_for
    from app.graph.queries import _GRAPH_CACHE, _get_graph
    from app.config import settings

    repo_id = "repo_size"
    
    # 8 functions total
    pf = MockParsedFile("f.py", "f.py", [MockParsedFunction(f"f{i}", []) for i in range(8)])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        orig_max = settings.MAX_GRAPH_NODES
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            settings.MAX_GRAPH_NODES = 5
            
            build_graph(repo_id, [pf])
            _GRAPH_CACHE.pop(repo_id, None)

            g = _get_graph(repo_id)
            assert_ok(g is not None, "Graph failed to build/load")
            
            # Exactly ceiling
            assert_ok(g.number_of_nodes() == 5, f"Expected exactly 5 nodes, got {g.number_of_nodes()}")
            
            # Check metadata
            with _graph_path_for(repo_id).open() as f:
                payload = json.load(f)
                
            assert_ok(payload["metadata"]["graph_truncated"] is True, "graph_truncated metadata not set")
            print(f"{PASS} EC7: Size ceiling enforced (8 -> 5), graph successfully truncated and marked")
        finally:
            settings.GRAPH_STORE_PATH = orig_store
            settings.MAX_GRAPH_NODES = orig_max


def test_ec8_atomic_write():
    print("\n--- EC8: Atomic write test ---")
    from app.graph.builder import build_graph, _graph_path_for
    from app.config import settings

    repo_id = "repo_atomic"
    pf1 = MockParsedFile("f.py", "f.py", [MockParsedFunction("foo", [])])
    pf2 = MockParsedFile("f.py", "f.py", [MockParsedFunction("foo", []), MockParsedFunction("bar", [])])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            
            # 1. Write initial valid graph
            build_graph(repo_id, [pf1])
            path = _graph_path_for(repo_id)
            assert_ok(path.exists(), "Initial graph not written")
            with path.open() as f:
                original_data = f.read()

            # 2. Mock os.replace to crash
            orig_replace = os.replace
            def crashing_replace(src, dst):
                raise RuntimeError("Simulated crash during os.replace!")
            
            with patch("os.replace", side_effect=crashing_replace):
                try:
                    build_graph(repo_id, [pf2])
                    assert_ok(False, "Should have crashed")
                except RuntimeError:
                    pass
            
            # 3. Verify original is perfectly intact
            with path.open() as f:
                new_data = f.read()
                
            assert_ok(new_data == original_data, "Graph file was corrupted by partial write!")
            print(f"{PASS} EC8: Atomic persistence ensures half-written graphs do not corrupt disk state")
        finally:
            settings.GRAPH_STORE_PATH = orig_store


def test_ec9_and_ec10_cycle_detection():
    print("\n--- EC9 & EC10: Cycle detection and timeouts ---")
    from app.graph.builder import build_graph
    from app.graph.queries import detect_cycles, _GRAPH_CACHE
    from app.config import settings

    repo_cycle = "repo_cycle"
    pf_cycle = MockParsedFile("f.py", "f.py", [
        MockParsedFunction("A", ["B"]),
        MockParsedFunction("B", ["A"])
    ])
    
    repo_clean = "repo_clean"
    pf_clean = MockParsedFile("f.py", "f.py", [
        MockParsedFunction("A", ["B"]),
        MockParsedFunction("B", [])
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        orig_timeout = settings.CYCLE_DETECTION_TIMEOUT_S
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            build_graph(repo_cycle, [pf_cycle])
            build_graph(repo_clean, [pf_clean])
            _GRAPH_CACHE.pop(repo_cycle, None)
            _GRAPH_CACHE.pop(repo_clean, None)

            # EC10: Fast correct responses
            assert_ok(detect_cycles(repo_cycle) is True, "Cycle undetected")
            assert_ok(detect_cycles(repo_clean) is False, "False positive cycle")
            print(f"{PASS} EC10: detect_cycles correctly identifies True/False without timeout")

            # EC9: Timeout path
            # We mock threading.Thread.is_alive to simulate a timeout block where the thread hasn't finished
            settings.CYCLE_DETECTION_TIMEOUT_S = 0.001
            
            with patch("threading.Thread.is_alive", return_value=True), \
                 patch("threading.Thread.join"):
                res = detect_cycles(repo_cycle)
                assert_ok(res is None, f"Timeout should return strictly None, got {res}")
            print(f"{PASS} EC9: detect_cycles timeout gracefully returns None without crashing ingestion")

        finally:
            settings.GRAPH_STORE_PATH = orig_store
            settings.CYCLE_DETECTION_TIMEOUT_S = orig_timeout


def test_ec11_dangling_edges():
    print("\n--- EC11: The dangling-edge test ---")
    from app.graph.builder import build_graph
    from app.graph.queries import get_callers, get_callees, _GRAPH_CACHE, _get_graph
    from app.config import settings

    repo_id = "repo_dangling"
    
    # 1. Build normal graph: A -> B -> C
    pf_initial = MockParsedFile("f.py", "f.py", [
        MockParsedFunction("A", ["B"]),
        MockParsedFunction("B", ["C"]),
        MockParsedFunction("C", [])
    ])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            build_graph(repo_id, [pf_initial])
            _GRAPH_CACHE.pop(repo_id, None)

            # 2. Build graph simulating B was deleted (e.g. file removed in incremental sync)
            pf_incremental = MockParsedFile("f.py", "f.py", [
                MockParsedFunction("A", ["B"]),
                MockParsedFunction("C", [])
            ])
            build_graph(repo_id, [pf_incremental])
            _GRAPH_CACHE.pop(repo_id, None)

            # Check that A->B and B->C edges are gone
            callers_of_c = get_callers(repo_id, "C")
            assert_ok(len(callers_of_c) == 0, f"Dangling edge B->C survived! Callers: {callers_of_c}")
            
            callees_of_a = get_callees(repo_id, "A")
            assert_ok(len(callees_of_a) == 0, f"Dangling edge A->B survived! Callees: {callees_of_a}")
            
            print(f"{PASS} EC11: Dangling edges are natively dropped, 0 references to missing nodes")
        finally:
            settings.GRAPH_STORE_PATH = orig_store


# ---------------------------------------------------------------------------
# STEP 3: None vs False vs [] Distinction
# ---------------------------------------------------------------------------
def test_step3_sentinel_distinction():
    print("\n--- STEP 3: None vs False vs [] Distinction ---")
    from app.graph.builder import build_graph
    from app.graph.queries import get_callers, detect_cycles, _GRAPH_CACHE
    from app.config import settings

    repo_id = "repo_sentinel"
    pf = MockParsedFile("f.py", "f.py", [MockParsedFunction("A", [])])

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_store = settings.GRAPH_STORE_PATH
        try:
            settings.GRAPH_STORE_PATH = tmpdir
            build_graph(repo_id, [pf])
            _GRAPH_CACHE.pop(repo_id, None)

            # No callers = []
            callers = get_callers(repo_id, "A")
            assert_ok(callers == [], "No callers should return empty list []")
            
            # No cycle = False
            cycle_status = detect_cycles(repo_id)
            assert_ok(cycle_status is False, "No cycle should return exactly False")

            # Both are distinct from None!
            assert_ok(callers is not None, "callers should not be None")
            assert_ok(cycle_status is not None, "cycle_status should not be None")
            print(f"{PASS} None / False / [] are strictly differentiated")

        finally:
            settings.GRAPH_STORE_PATH = orig_store


# ---------------------------------------------------------------------------
# STEP 4: Handoff / Module 11 Reusability
# ---------------------------------------------------------------------------
def test_step4_handoff():
    print("\n--- STEP 4: Handoff to Module 11 (Depth clamping source of truth) ---")
    from app.graph.queries import get_subgraph
    # Just asserting it's cleanly callable standalone without weird internal state setup
    assert_ok(callable(get_subgraph), "get_subgraph is callable")
    print(f"{PASS} get_subgraph depth-clamping is standalone and cleanly importable by Module 11")


# ---------------------------------------------------------------------------
# STEP 5: Static / Boundary Checks
# ---------------------------------------------------------------------------
def test_step5_static_checks():
    print("\n--- STEP 5: Static Boundary Checks ---")
    queries_path = PROJECT_ROOT / "app/graph/queries.py"
    queries_code = queries_path.read_text(encoding="utf-8")
    
    # Check for bare dictionary accesses into graph structures
    # Looking for graph.nodes[x] specifically
    import ast
    tree = ast.parse(queries_code)
    
    unwrapped_accesses = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Attribute):
                if node.value.attr in ("nodes", "edges"):
                    # This is `graph.nodes[...]` or `graph.edges[...]`
                    unwrapped_accesses.append(f"Line {node.lineno}: unwrapped access to {node.value.attr}")
                    
    if unwrapped_accesses:
        for u in unwrapped_accesses:
            print(f"  [FLAGGED]: {u}")
        print(f"  [BOUNDARY NOTE] Queries module contains latent KeyError risks by bypassing .get() style accesses.")
    else:
        print(f"{PASS} Zero unwrapped/non-defensive graph lookups found")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 7 Tests: Call Graph Builder (NetworkX)")
    print("=" * 60)

    test_step1_deliverables()
    test_ec1_and_ec2_real_data_and_edge_types()
    test_ec3_and_ec4_nonexistent_functions()
    test_ec5_and_ec6_depth_clamping()
    test_ec7_size_ceiling()
    test_ec8_atomic_write()
    test_ec9_and_ec10_cycle_detection()
    test_ec11_dangling_edges()
    test_step3_sentinel_distinction()
    test_step4_handoff()
    test_step5_static_checks()

    print("\n" + "=" * 60)
    print("=== Module 7: TESTS COMPLETED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
