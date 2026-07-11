# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""Bootstrap sys.path and expose app.config.settings for scripts."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

__all__ = ["ROOT", "settings"]
