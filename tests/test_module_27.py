# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #27 — onboarding path generator tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from app.agent.onboarding_path import (
    MAX_RATIONALE_FILES,
    build_path,
    generate_rationale,
    rank_central_files,
)


def _sample_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_node("app/api/router.py:chat", path="app/api/router.py", name="chat")
    g.add_node("app/main.py:main", path="app/main.py", name="main")
    g.add_node("frontend/App.tsx:App", path="frontend/App.tsx", name="App")
    g.add_edge("app/main.py:main", "app/api/router.py:chat")
    g.add_edge("app/api/router.py:chat", "app/main.py:main")
    return g


def test_rank_central_files_backend_role():
    ranked = rank_central_files(_sample_graph(), "backend")
    assert "app/api/router.py" in ranked
    assert "frontend/App.tsx" not in ranked


def test_rank_central_files_empty_role_filter_falls_back():
    g = nx.DiGraph()
    g.add_node("only/frontend/x.tsx:f", path="only/frontend/x.tsx", name="f")
    ranked = rank_central_files(g, "backend")
    assert ranked == ["only/frontend/x.tsx"]


def test_build_path_output_contract(tmp_path):
    graph = _sample_graph()
    cache_dir = tmp_path / "repo1" / ".onboarding_path_cache"
    cache_dir.mkdir(parents=True)

    with patch("app.agent.onboarding_path._get_commit_hash", return_value="abc123"), patch(
        "app.agent.onboarding_path._get_graph", return_value=graph
    ), patch("app.agent.onboarding_path._load_cached_path", return_value=None), patch(
        "app.agent.onboarding_path.check_file_existence", return_value=True
    ), patch(
        "app.agent.onboarding_path.generate_rationale", return_value="Because it wires HTTP entrypoints."
    ), patch.object(
        __import__("app.agent.onboarding_path", fromlist=["settings"]).settings,
        "REPOS_PATH",
        str(tmp_path),
    ):
        out = build_path("repo1", "backend", "junior")

    assert out
    item = out[0]
    assert set(item.keys()) == {
        "file_path",
        "why_it_matters",
        "suggested_order",
        "related_functions",
    }
    assert item["suggested_order"] == 1
    assert isinstance(item["related_functions"], list)


def test_build_path_cache_hit_skips_work(tmp_path):
    cached = [{
        "file_path": "app/main.py",
        "why_it_matters": "cached",
        "suggested_order": 1,
        "related_functions": ["main"],
    }]
    with patch("app.agent.onboarding_path._get_commit_hash", return_value="abc"), patch(
        "app.agent.onboarding_path._load_cached_path", return_value=cached
    ) as mock_load, patch("app.agent.onboarding_path._get_graph") as mock_graph, patch(
        "app.agent.onboarding_path.generate_rationale"
    ) as mock_rat:
        out = build_path("repo1", "backend", "junior")

    assert out == cached
    mock_graph.assert_not_called()
    mock_rat.assert_not_called()
    mock_load.assert_called_once()


def test_generate_rationale_discards_bad_file_refs():
    with patch("app.agent.onboarding_path.check_file_existence", return_value=True), patch(
        "app.agent.onboarding_path.get_llm_client"
    ) as mock_llm, patch(
        "app.agent.onboarding_path._rationale_passes_file_checks",
        side_effect=[False, True],
    ):
        client = MagicMock()
        client.create.return_value = MagicMock(
            content=[{"type": "text", "text": "See `fake/missing.py:1-2` for details."}]
        )
        mock_llm.return_value = client
        text = generate_rationale("app/main.py", "backend", repo_id="repo1")

    assert "app/main.py" in text
    assert "fake/missing.py" not in text


def test_max_rationale_files_bounded():
    assert MAX_RATIONALE_FILES == 10
