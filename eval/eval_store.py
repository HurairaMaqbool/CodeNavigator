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
import uuid
from pathlib import Path
from typing import Any

HISTORY_JSON = Path("tests/eval_results.json")
HISTORY_JSONL = Path("tests/eval_history.jsonl")


def _stable_run_id(run: dict[str, Any], index: int) -> str:
    """Derive a stable unique id for a persisted run (legacy rows included)."""
    existing = run.get("run_id")
    if existing:
        return str(existing)
    ts = str(run.get("timestamp") or "").strip()
    ver = str(run.get("version") or "unknown").strip()
    if ts:
        return f"{ver}::{ts}"
    return f"{ver}::idx{index}"


def _normalize_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach unique ``run_id`` to every row; disambiguate rare collisions."""
    normalized: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(runs):
        run = dict(raw)
        run_id = _stable_run_id(run, index)
        if run_id in seen:
            seen[run_id] += 1
            run_id = f"{run_id}#{seen[run_id]}"
        else:
            seen[run_id] = 0
        run["run_id"] = run_id
        normalized.append(run)
    return normalized


def load_runs(*, newest_first: bool = False) -> list[dict[str, Any]]:
    if HISTORY_JSON.exists():
        try:
            with HISTORY_JSON.open("r", encoding="utf-8") as f:
                runs = json.load(f)
            if isinstance(runs, list) and runs:
                ordered = list(reversed(runs)) if newest_first else runs
                return _normalize_runs(ordered)
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
    ordered = list(reversed(records)) if newest_first else records
    return _normalize_runs(ordered)


def get_run(version_or_run_id: str) -> dict[str, Any] | None:
    for run in load_runs():
        if run.get("run_id") == version_or_run_id or run.get("version") == version_or_run_id:
            return run
    return None


def append_run(record: dict[str, Any]) -> dict[str, Any]:
    """Append a run to history (JSON + JSONL) and return the record."""
    HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not record.get("run_id"):
        record = {**record, "run_id": uuid.uuid4().hex}
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
