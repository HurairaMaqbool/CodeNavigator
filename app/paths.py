# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/paths.py
------------
Single root for all on-disk platform/state paths derived from ``settings.DATA_PATH``.

Every module that previously used ``Path("data/...")`` must import from here so
deployments can relocate storage via one env var (``DATA_PATH``).
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings


def data_path(*parts: str) -> Path:
    """Resolve a path under the configured DATA_PATH root."""
    root = Path(settings.DATA_PATH)
    if not parts:
        return root
    return root.joinpath(*parts)


def ensure_data_dir() -> Path:
    """Create DATA_PATH if missing; return the root."""
    root = data_path()
    root.mkdir(parents=True, exist_ok=True)
    return root
