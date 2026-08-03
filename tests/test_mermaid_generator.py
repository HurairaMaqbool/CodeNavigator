# Copyright (c) 2026 Huraira Maqbool
# Dedicated regression test for app/diagrams/mermaid_generator.py

import pytest
from app.diagrams.mermaid_generator import generate_mermaid

def test_mermaid_generator_large_subgraph_late_alphabet_entry():
    """
    Regression Test for Track B3:
    Verifies that generate_mermaid correctly preserves an entry point node whose ID starts
    alphabetically late (e.g. 'z_module.py:late_entry_point') when max_nodes limit is enforced,
    renders its connected edges, and avoids producing disconnected single nodes.
    """
    entry_id = "z_module.py:late_entry_point"

    # Build a 40-node synthetic subgraph where nodes start with 'a_module.py:...', 'b_module.py:...', etc.
    nodes = [{"id": f"a_module_{i}.py:func_{i}", "path": f"a_module_{i}.py", "name": f"func_{i}"} for i in range(35)]
    nodes.append({"id": entry_id, "path": "z_module.py", "name": "late_entry_point"})
    for i in range(4):
        nodes.append({"id": f"z_callee_{i}.py:target_{i}", "path": f"z_callee_{i}.py", "name": f"target_{i}"})

    # Edges from entry_id to callees and between a_modules
    edges = [
        {"source": entry_id, "target": f"z_callee_{i}.py:target_{i}"} for i in range(4)
    ]
    for i in range(10):
        edges.append({"source": f"a_module_{i}.py:func_{i}", "target": f"a_module_{i+1}.py:func_{i+1}"})

    subgraph = {
        "entry_point": entry_id,
        "nodes": nodes,
        "edges": edges
    }

    mermaid_out = generate_mermaid(subgraph, direction="both", max_nodes=15)

    # 1. Entry point MUST be present in rendered Mermaid
    assert "late_entry_point" in mermaid_out, "Entry point symbol missing from Mermaid output!"

    # 2. Connected edges MUST be rendered with '-->'
    assert "-->" in mermaid_out, "No edges rendered in Mermaid output!"
    assert "late_entry_point" in mermaid_out and "target_0" in mermaid_out

    # 3. Disconnected single nodes MUST NOT be rendered
    lines = [line.strip() for line in mermaid_out.splitlines() if line.strip() and not line.strip().startswith("graph") and not line.strip().startswith("note") and not line.strip().startswith("class")]
    for line in lines:
        assert "-->" in line or "-.->" in line, f"Found disconnected single node line without edge: {line!r}"

def test_mermaid_generator_empty_or_small():
    """Verify small subgraphs render cleanly."""
    subgraph = {
        "entry_point": "a.py:foo",
        "nodes": [
            {"id": "a.py:foo", "path": "a.py", "name": "foo"},
            {"id": "b.py:bar", "path": "b.py", "name": "bar"},
        ],
        "edges": [
            {"source": "a.py:foo", "target": "b.py:bar"}
        ]
    }

    mermaid_out = generate_mermaid(subgraph, direction="both")
    assert "a.py:foo" in mermaid_out
    assert "b.py:bar" in mermaid_out
    assert "-->" in mermaid_out
