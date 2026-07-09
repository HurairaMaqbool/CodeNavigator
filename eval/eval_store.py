# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
eval/eval_store.py
------------------
Unified persistence for RAGAS evaluation runs.

All readers (compare, history API, Streamlit) and writers (run_eval) use this
module so version ids never drift across files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HISTORY_JSON = Path("tests/eval_results.json")
HISTORY_JSONL = Path("tests/eval_history.jsonl")


def load_runs(*, newest_first: bool = False) -> list[dict[str, Any]]:
    if HISTORY_JSON.exists():
        try:
            with HISTORY_JSON.open("r", encoding="utf-8") as f:
                runs = json.load(f)
            if isinstance(runs, list) and runs:
                return list(reversed(runs)) if newest_first else runs
        except Exception:
            pass

    if not HISTORY_JSONL.exists():
        return []

    records: list[dict[str, Any]] = []
    with HISTORY_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if newest_first:
        return list(reversed(records))
    return records


def get_run(version: str) -> dict[str, Any] | None:
    for run in load_runs():
        if run.get("version") == version:
            return run
    return None


def append_run(record: dict[str, Any]) -> dict[str, Any]:
    """Append a run to history (JSON + JSONL) and return the record."""
    HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    runs = load_runs()
    runs.append(record)
    with HISTORY_JSON.open("w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)
    try:
        with HISTORY_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
    return record


def update_last_run(updates: dict[str, Any]) -> None:
    """Patch fields on the most recent run (e.g. regression_warning after save)."""
    runs = load_runs()
    if not runs:
        return
    runs[-1].update(updates)
    with HISTORY_JSON.open("w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2)
