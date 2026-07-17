# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/agent/prompts/loader.py
---------------------------
IP-protection loader to dynamically read proprietary prompt templates and datasets
from the git-ignored /private/ folder, falling back to basic public templates.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRIVATE_DIR = Path(__file__).resolve().parents[3] / "private"

def load_private_prompt(filename: str, fallback: str) -> str:
    """Load a text prompt from private directory if available, otherwise use fallback."""
    path = PRIVATE_DIR / "prompts" / filename
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return fallback.strip()


def load_private_json(filename: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Load a JSON dataset from private directory if available, otherwise use fallback."""
    path = PRIVATE_DIR / "data" / filename
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return fallback
