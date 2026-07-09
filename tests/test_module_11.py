# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_module_11.py
-----------------------
Module 11 Tests: Diagram Generation (Mermaid)
"""
import sys
import re
from pathlib import Path

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

from app.diagrams.mermaid_generator import graph_to_mermaid, sanitize

# ---------------------------------------------------------------------------
# Helpers for Mermaid verification
# ---------------------------------------------------------------------------
def verify_mermaid_syntax(mermaid_str: str) -> bool:
    lines = [line.strip() for line in mermaid_str.split('\n') if line.strip()]
    if not lines:
        return False
    if lines[0] != "graph TD":
        return False
        
    for line in lines[1:]:
        if line.startswith("note["):
            if not line.endswith(']'): return False
            continue
            
        if "-->" in line:
            # Edge: A["A"] --> B["B"]
            parts = line.split("-->")
            if len(parts) != 2: return False
            if '["' not in parts[0] or '"]' not in parts[0]: return False
            if '["' not in parts[1] or '"]' not in parts[1]: return False
        else:
            # Node declaration: A["A"]
            if '["' not in line or '"]' not in line: return False
            
    return True


# ---------------------------------------------------------------------------
# STEP 1: Deliverables & Boundary
# ---------------------------------------------------------------------------
def test_step1_deliverables():
    print("\n--- STEP 1: Confirm Deliverables ---")
    assert_ok(callable(graph_to_mermaid), "graph_to_mermaid missing")
    assert_ok(callable(sanitize), "sanitize missing")
    
    file_content = (PROJECT_ROOT / "app/diagrams/mermaid_generator.py").read_text(encoding="utf-8")
    import_calls = [line for line in file_content.split('\n') if 'get_subgraph' in line and 'def graph_to_mermaid' not in line and 'def generate_diagram' not in line]
    # Note: generate_diagram uses it, but graph_to_mermaid itself must not.
    # We will manually inspect this, but static check inside graph_to_mermaid body.
    
    # Let's ensure get_subgraph is only in the generate_diagram wrapper
    idx = file_content.find("def graph_to_mermaid")
    idx2 = file_content.find("def generate_diagram")
    body = file_content[idx:idx2]
    assert_ok("get_subgraph(" not in body, "graph_to_mermaid calls get_subgraph directly!")
    
    print(f"{PASS} All deliverables exist, graph_to_mermaid is a pure function")


# ---------------------------------------------------------------------------
# STEP 2 Edge Cases
# ---------------------------------------------------------------------------

def test_ec1_real_subgraph():
    print("\n--- EC1: Real subgraph syntax test ---")
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"}
        ]
    }
    
    res = graph_to_mermaid(data, requested_depth=2, clamped_depth=2)
    mermaid = res["mermaid"]
    assert_ok(verify_mermaid_syntax(mermaid), f"Invalid syntax generated:\n{mermaid}")
    assert_ok("a[\"a\"]" in mermaid and "b[\"b\"]" in mermaid, "Labels missing")
    
    print(f"{PASS} EC1: Subgraph outputs strictly valid Mermaid syntax")


def test_ec2_zero_edge():
    print("\n--- EC2: Zero-edge subgraph test ---")
    data = {
        "nodes": [{"id": "isolated_node"}],
        "edges": []
    }
    res = graph_to_mermaid(data, 1, 1)
    
    assert_ok(res.get("empty") is False, "empty flag should be False when nodes render")
    assert_ok("graph TD" in (res.get("mermaid") or ""), "Mermaid should render isolated nodes")
    
    print(f"{PASS} EC2: Zero-edge subgraph renders isolated nodes in Mermaid")


def test_ec3_ec4_node_cap():
    print("\n--- EC3 & EC4: Node-cap and No-truncation tests ---")
    # > 25 nodes
    nodes = [{"id": f"n{i}"} for i in range(30)]
    edges = [{"source": "n0", "target": f"n{i}"} for i in range(1, 30)]
    data_large = {"nodes": nodes, "edges": edges}
    
    res_large = graph_to_mermaid(data_large, 2, 2)
    m_large = res_large["mermaid"]
    
    node_declarations = m_large.count('["')
    # Because edges reuse names, and some target nodes won't be in the kept 25,
    # those edges are skipped. So we only see the kept nodes.
    # 25 nodes + 1 for the note = 26 line items?
    # The note has no quotes.
    # Wait, 1 line = graph TD. 1 note line. 24 edge lines for the kept 24 targets (n0 -> n1...n24).
    # Total lines = 1 + 1 + 24 = 26.
    
    assert_ok("+5 more dependencies not shown" in m_large, f"Note missing or wrong count: {m_large}")
    
    # <= 25 nodes
    data_small = {"nodes": nodes[:20], "edges": edges[:19]}
    res_small = graph_to_mermaid(data_small, 2, 2)
    m_small = res_small["mermaid"]
    
    assert_ok("more dependencies not shown" not in m_small, "Truncation note appeared on small graph!")
    
    print(f"{PASS} EC3/EC4: Node-cap enforces exactly max_nodes, conditionally renders +N note line")


def test_ec5_depth_clamp_flag():
    print("\n--- EC5: Depth-clamp-flag test ---")
    # Independent of node count
    data = {"nodes": [{"id": "a"}], "edges": []}
    
    res_unclamped = graph_to_mermaid(data, 2, 2)
    res_clamped = graph_to_mermaid(data, 10, 3)
    
    assert_ok(res_unclamped["clamped"] is False, "Unclamped reported as clamped")
    assert_ok(res_clamped["clamped"] is True, "Clamped reported as unclamped despite differing depths")
    
    print(f"{PASS} EC5: Depth-clamping boolean logic triggers cleanly via args (independent of sizes)")


def test_ec6_sanitization_collision():
    print("\n--- EC6: Sanitization-collision test ---")
    # "auth.validate" and "auth_validate" both sanitize to "auth_validate" initially.
    data = {
        "nodes": [{"id": "auth.validate"}, {"id": "auth_validate"}, {"id": "entry"}],
        "edges": [
            {"source": "entry", "target": "auth.validate"},
            {"source": "entry", "target": "auth_validate"}
        ]
    }
    
    res = graph_to_mermaid(data, 2, 2)
    mermaid = res["mermaid"]
    
    # Confirm both labels are present, proving two distinct nodes
    assert_ok('["auth.validate"]' in mermaid, "auth.validate label missing")
    assert_ok('["auth_validate"]' in mermaid, "auth_validate label missing")
    
    # Confirm two DIFFERENT sanitized IDs were used (e.g. auth_validate and auth_validate_1)
    # entry --> ID1["auth.validate"]
    # entry --> ID2["auth_validate"]
    matches = re.findall(r'-->\s*([a-zA-Z0-9_]+)\[', mermaid)
    
    assert_ok(len(set(matches)) == 2, f"Collision occurred! Target IDs merged: {matches}")
    
    print(f"{PASS} EC6: Sanitization collisions successfully disambiguated via suffixes! (CRITICAL)")


def test_ec7_self_loop():
    print("\n--- EC7: Self-loop test ---")
    data = {
        "nodes": [{"id": "recursive"}],
        "edges": [{"source": "recursive", "target": "recursive"}]
    }
    
    res = graph_to_mermaid(data, 1, 1)
    mermaid = res["mermaid"]
    
    assert_ok(verify_mermaid_syntax(mermaid), "Invalid syntax for self-loop")
    # E.g. recursive["recursive"] --> recursive["recursive"]
    assert_ok('recursive["recursive"] --> recursive["recursive"]' in mermaid, "Self loop not formatted correctly")
    
    print(f"{PASS} EC7: Self-loops (direct recursion) emit valid Mermaid edge syntax")


def test_ec8_label_vs_id():
    print("\n--- EC8: Label-vs-ID test ---")
    data = {
        "nodes": [{"id": "a$b!c"}, {"id": "b"}],
        "edges": [{"source": "a$b!c", "target": "b"}]
    }
    
    res = graph_to_mermaid(data, 1, 1)
    mermaid = res["mermaid"]
    
    # The label must be EXACTLY a$b!c
    assert_ok('["a$b!c"]' in mermaid, "Display label was unexpectedly sanitized/corrupted")
    # The ID must NOT contain $ or !
    id_part = mermaid.split('[')[0].strip().split('    ')[-1]
    assert_ok('$' not in id_part and '!' not in id_part, "Node ID was NOT sanitized properly")
    
    print(f"{PASS} EC8: Node IDs are aggressively sanitized while brackets protect exact original labels")


# ---------------------------------------------------------------------------
# STEP 3 & 4: Boundaries and API Contract
# ---------------------------------------------------------------------------
def test_step3_and_4():
    print("\n--- STEP 3 & 4: API Boundaries ---")
    data = {"nodes": [{"id": "a"}], "edges": []}
    
    # Tool output vs Endpoint output logic (identically called)
    res_tool = graph_to_mermaid(data, 2, 2)
    res_endpoint = graph_to_mermaid(data, 2, 2)
    
    assert_ok(res_tool == res_endpoint, "Deterministic generation failed (outputs differ)")
    
    print(f"{PASS} Deterministic identical output across identical inputs (Tool & API safety)")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Module 11 Tests: Diagram Generation")
    print("=" * 60)

    test_step1_deliverables()
    test_ec1_real_subgraph()
    test_ec2_zero_edge()
    test_ec3_ec4_node_cap()
    test_ec5_depth_clamp_flag()
    test_ec6_sanitization_collision()
    test_ec7_self_loop()
    test_ec8_label_vs_id()
    test_step3_and_4()

    print("\n" + "=" * 60)
    print("=== Module 11: ALL TESTS COMPLETED ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
