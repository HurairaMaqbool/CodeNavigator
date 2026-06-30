"""
app/evaluation/compare_runs.py
------------------------------
Appends RAGAS evaluation results to history and provides regression tracking.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_FILE = Path("tests/eval_history.jsonl")

def append_to_history(payload: dict[str, Any], version: str = "auto", git_sha: str = "unknown") -> None:
    """
    Appends the latest run metrics to the JSONL history file.
    """
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    record = {
        "version": version,
        "git_sha": git_sha,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload
    }
    
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def compare_eval_runs(baseline_version: str, candidate_version: str, tolerance: float = 0.05) -> dict[str, Any]:
    """
    Diffs two versions from the history file and flags regressions.
    """
    if not HISTORY_FILE.exists():
        raise FileNotFoundError("History file does not exist.")
        
    records = []
    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
                
    baseline = next((r for r in reversed(records) if r["version"] == baseline_version), None)
    candidate = next((r for r in reversed(records) if r["version"] == candidate_version), None)
    
    if not baseline:
        raise KeyError(f"Baseline version '{baseline_version}' not found in history.")
    if not candidate:
        raise KeyError(f"Candidate version '{candidate_version}' not found in history.")
        
    diffs = {}
    regressions = []
    
    for key in baseline.get("ragas_scores", {}):
        b_val = baseline["ragas_scores"].get(key, 0.0)
        c_val = candidate.get("ragas_scores", {}).get(key, 0.0)
        delta = c_val - b_val
        diffs[key] = {"baseline": b_val, "candidate": c_val, "delta": delta}
        if delta < -tolerance:
            regressions.append(key)
            
    passed = len(regressions) == 0
    if not passed:
        from app.observability.logging_config import logger
        logger.error("ragas_regression_detected", regressions=regressions, diffs=diffs)
        # Note: In a CI environment, you may want to raise an exception or exit(1) here
        # so the build fails if model accuracy degrades below thresholds.
            
    return {
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "diffs": diffs,
        "regressions": regressions,
        "passed": passed
    }
