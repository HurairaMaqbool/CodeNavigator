# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Regression tests for local embedding/reranker model loading."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_embedding_model_uses_non_meta_load_kwargs(monkeypatch):
    import app.retrieval.embeddings as emb

    monkeypatch.setattr(emb, "_MODEL", None)
    captured: dict = {}

    class _FakeST:
        def __init__(self, model_name, *, device=None, model_kwargs=None, **kwargs):
            captured["model_name"] = model_name
            captured["device"] = device
            captured["model_kwargs"] = model_kwargs

        def encode(self, sentences, normalize_embeddings=True):
            return [[0.1, 0.2]]

    with patch("sentence_transformers.SentenceTransformer", _FakeST):
        model = emb.get_model()

    assert model is not None
    assert captured["device"] == "cpu"
    assert captured["model_kwargs"] == {"low_cpu_mem_usage": False}


def test_reranker_model_uses_non_meta_load_kwargs(monkeypatch):
    import app.retrieval.reranker as rr

    monkeypatch.setattr(rr, "_RERANKER_MODEL", None)
    captured: dict = {}

    class _FakeCE:
        def __init__(self, model_name, *, device=None, automodel_args=None, **kwargs):
            captured["model_name"] = model_name
            captured["device"] = device
            captured["automodel_args"] = automodel_args

        def predict(self, pairs, show_progress_bar=False):
            return [0.5]

    with patch("sentence_transformers.CrossEncoder", _FakeCE):
        model = rr.get_model()

    assert model is not None
    assert captured["device"] == "cpu"
    assert captured["automodel_args"] == {"low_cpu_mem_usage": False}


def test_on_startup_raises_when_embedding_load_fails(monkeypatch):
    from app.main import on_startup

    def _boom():
        raise RuntimeError("Cannot copy out of meta tensor")

    monkeypatch.setattr("app.retrieval.embeddings.get_model", _boom)
    with pytest.raises(RuntimeError, match="meta tensor"):
        on_startup()
