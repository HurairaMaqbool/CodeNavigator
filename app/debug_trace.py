"""Session debug logging for agent-assisted troubleshooting."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import settings

_LOG_PATH = Path(settings.REPOS_PATH).parent / "debug-fda280.log"
_SESSION_ID = "fda280"


def debug_log(
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # region agent log
    try:
        entry = {
            "sessionId": _SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    # endregion
