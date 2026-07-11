# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #20 verification — mermaid_generator + POST /diagram pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.diagrams.mermaid_generator import generate_mermaid, graph_to_mermaid, sanitize_node_label
from app.main import app


def test_sanitize_node_label_special_chars():
    raw = 'foo"bar[baz]|(x)\nline'
    out = sanitize_node_label(raw)
    assert '"' not in out
    assert "[" not in out
    assert "]" not in out
    assert "|" not in out
    assert "(" not in out
    assert ")" not in out
    assert "\n" not in out
    assert "&quot;" in out
    assert "&#91;" in out


def test_generate_mermaid_empty_subgraph_not_found():
    mermaid = generate_mermaid(
        {"nodes": [], "edges": [], "not_found": True, "entry_point": "missing_fn"},
        direction="both",
    )
    assert mermaid.startswith("graph TD")
    assert "no connections found" in mermaid
    assert "missing_fn" in mermaid
    assert mermaid.strip()


def test_generate_mermaid_zero_edges_single_entry():
    mermaid = generate_mermaid(
        {
            "nodes": [{"id": "isolated_node", "name": "isolated_node"}],
            "edges": [],
            "entry_point": "isolated_node",
        },
        direction="both",
    )
    assert "no connections found" in mermaid
    assert "isolated_node" in mermaid


def test_generate_mermaid_cycle_highlight():
    subgraph = {
        "nodes": [{"id": "a", "name": "a"}, {"id": "b", "name": "b"}],
        "edges": [{"source": "a", "target": "b"}],
        "entry_point": "a",
    }
    with patch("app.graph.queries.get_cycle_info", return_value=[["a", "b", "a"]]):
        mermaid = generate_mermaid(subgraph, direction="both", repo_id="repo-1")
    assert "-.->|cycle|" in mermaid
    assert "classDef cycleNode" in mermaid


def test_generate_mermaid_distinct_ids_for_same_basename():
    subgraph = {
        "nodes": [
            {"id": "src/a/foo.py:bar", "name": "bar"},
            {"id": "src/b/foo.py:bar", "name": "bar"},
            {"id": "entry", "name": "entry"},
        ],
        "edges": [
            {"source": "entry", "target": "src/a/foo.py:bar"},
            {"source": "entry", "target": "src/b/foo.py:bar"},
        ],
        "entry_point": "entry",
    }
    mermaid = generate_mermaid(subgraph, direction="downstream")
    assert mermaid.startswith("graph LR")
    import re
    target_ids = re.findall(r"-->\s*([a-zA-Z0-9_]+)\[", mermaid)
    assert len(set(target_ids)) == 2


def test_post_diagram_endpoint_returns_mermaid(mock_api_key):
    client = TestClient(app)
    meta = MagicMock()
    meta.sync_status = "synced"
    meta.commit_hash = "abc"
    meta.org_id = "default"

    subgraph = {
        "nodes": [{"id": "main", "name": "main"}],
        "edges": [],
        "requested_depth": 2,
        "clamped": False,
    }

    with patch("app.api.router._resolve_repo_meta", return_value=(meta, "asset-id")), patch(
        "app.api.router._require_repo_ready", return_value=None
    ), patch("app.api.router.get_subgraph", return_value=subgraph), patch(
        "app.api.router.generate_mermaid",
        return_value='graph TD\n    main["main: no connections found"]',
    ) as mock_gen:
        resp = client.post(
            "/diagram",
            headers={"X-API-Key": "dev-secret-key"},
            json={"repo_id": "job-1", "entry_point": "main", "direction": "both"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "mermaid_markdown" in body
    mock_gen.assert_called_once()
    call_sub = mock_gen.call_args[0][0]
    assert call_sub["entry_point"] == "main"


def test_graph_to_mermaid_contract():
    res = graph_to_mermaid(
        {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]},
        requested_depth=2,
        clamped_depth=2,
    )
    assert isinstance(res["mermaid"], str)
    assert res["mermaid"].startswith("graph")
