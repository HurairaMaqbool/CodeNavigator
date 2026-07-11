# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Centralized paths and language registry regression tests."""
from __future__ import annotations

from app.ingestion.language_registry import EXTENSION_TO_LANGUAGE, language_for_path
from app.ingestion.file_filter import EXTENSION_TO_LANGUAGE as FILTER_EXTENSIONS
from app.paths import data_path
from app.config import settings


def test_language_registry_matches_file_filter():
    assert FILTER_EXTENSIONS is EXTENSION_TO_LANGUAGE


def test_language_for_path_python():
    assert language_for_path("src/main.py") == "python"


def test_data_path_uses_settings_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PATH", str(tmp_path))
    assert data_path("api_keys.json") == tmp_path / "api_keys.json"
