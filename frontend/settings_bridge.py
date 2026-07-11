# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
frontend/settings_bridge.py
-----------------------------
Expose backend ``app.config.settings`` to the Streamlit frontend.

Rule: frontend must NOT call os.environ directly — import settings here so
tuning stays centralized in app/config.py + .env.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings  # noqa: E402

__all__ = ["settings"]
