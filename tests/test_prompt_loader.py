# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
tests/test_prompt_loader.py
---------------------------
Unit tests for the IP-protected prompt and dataset loader.
"""
from __future__ import annotations

from pathlib import Path
import pytest
from app.agent.prompts.loader import load_private_prompt, load_private_json


def test_loader_falls_back():
    res = load_private_prompt("nonexistent_prompt_file_xyz.txt", "my fallback")
    assert res == "my fallback"


def test_loader_loads_private(tmp_path):
    import app.agent.prompts.loader as loader
    original_dir = loader.PRIVATE_DIR
    loader.PRIVATE_DIR = tmp_path

    try:
        # Create mock directories
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "test_prompt.txt").write_text("hello custom prompt", encoding="utf-8")

        res = load_private_prompt("test_prompt.txt", "fallback")
        assert res == "hello custom prompt"
    finally:
        loader.PRIVATE_DIR = original_dir


def test_loader_json_fallback():
    res = load_private_json("nonexistent_json_xyz.json", {"fallback": True})
    assert res == {"fallback": True}


def test_loader_json_loads_private(tmp_path):
    import app.agent.prompts.loader as loader
    original_dir = loader.PRIVATE_DIR
    loader.PRIVATE_DIR = tmp_path

    try:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "test_data.json").write_text('{"custom": true}', encoding="utf-8")

        res = load_private_json("test_data.json", {"fallback": True})
        assert res == {"custom": True}
    finally:
        loader.PRIVATE_DIR = original_dir
