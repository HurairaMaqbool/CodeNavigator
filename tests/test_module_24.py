# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Module #24 — semantic_cache check_cache / store contract tests."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.agent.semantic_cache import (
    CACHE_HIT_SIMILARITY_THRESHOLD,
    check_cache,
    store,
)


@pytest.fixture
def mock_chroma_col():
    col = MagicMock()
    col.count.return_value = 1
    with patch("app.agent.semantic_cache._get_cache_collection", return_value=col):
        yield col


def test_check_cache_hit_shape(mock_chroma_col):
    mock_chroma_col.query.return_value = {
        "ids": [["id1"]],
        "distances": [[0.02]],  # similarity 0.98
        "metadatas": [[{
            "answer_json": json.dumps({
                "answer": "cached text",
                "sources": [{"file_path": "a.py"}],
                "confidence_score": 0.91,
                "gated": False,
            }),
            "repo_commit_hash": "abc123",
            "timestamp": int(time.time()),
        }]],
    }
    with patch("app.agent.semantic_cache.embed", return_value=[0.1, 0.2]):
        hit = check_cache("How does auth work?", "repo1", "abc123")

    assert hit is not None
    assert set(hit.keys()) == {"answer", "sources", "confidence_score"}
    assert hit["answer"] == "cached text"
    assert hit["confidence_score"] == 0.91


def test_check_cache_miss_below_threshold(mock_chroma_col):
    mock_chroma_col.query.return_value = {
        "ids": [["id1"]],
        "distances": [[0.10]],  # similarity 0.90 < 0.95
        "metadatas": [[{
            "answer_json": json.dumps({"answer": "x", "gated": False}),
            "repo_commit_hash": "abc123",
            "timestamp": int(time.time()),
        }]],
    }
    with patch("app.agent.semantic_cache.embed", return_value=[0.1, 0.2]):
        assert check_cache("different question", "repo1", "abc123") is None


def test_check_cache_miss_wrong_commit(mock_chroma_col):
    mock_chroma_col.query.return_value = {
        "ids": [["id1"]],
        "distances": [[0.01]],
        "metadatas": [[{
            "answer_json": json.dumps({"answer": "stale", "gated": False}),
            "repo_commit_hash": "old_commit",
            "timestamp": int(time.time()),
        }]],
    }
    with patch("app.agent.semantic_cache.embed", return_value=[0.1, 0.2]):
        assert check_cache("q", "repo1", "new_commit") is None


def test_store_rejects_gated():
    with patch("app.agent.semantic_cache._get_cache_collection") as mock_get:
        store("q", {"answer": "no", "gated": True}, "repo1", "abc", gated=True)
        mock_get.assert_not_called()


def test_store_rejects_gated_in_payload():
    with patch("app.agent.semantic_cache._get_cache_collection") as mock_get:
        store("q", {"answer": "no", "gated": True}, "repo1", "abc")
        mock_get.assert_not_called()


def test_store_writes_verified_answer(mock_chroma_col):
    with patch("app.agent.semantic_cache.embed", return_value=[0.5, 0.5]):
        store(
            "How does auth work?",
            {"answer": "verified", "sources": [], "confidence_score": 0.88, "gated": False},
            "repo1",
            "abc123",
            gated=False,
        )
    mock_chroma_col.add.assert_called_once()
    meta = mock_chroma_col.add.call_args[1]["metadatas"][0]
    assert meta["repo_commit_hash"] == "abc123"
    payload = json.loads(meta["answer_json"])
    assert payload["gated"] is False


def test_threshold_is_named_constant():
    assert CACHE_HIT_SIMILARITY_THRESHOLD == 0.95
