#!/usr/bin/env python3
"""
validate_module2_live.py
------------------------
End-to-end live validation for Module 2 (Observability).

Run AFTER:  pip install -r requirements.txt

What this tests
~~~~~~~~~~~~~~~
1. /health returns HTTP 200 with {"status": "ok"}.
2. Every response carries an X-Request-ID header.
3. Each request produces a DISTINCT request_id (no ID reuse).
4. The stdout log lines are valid JSON.
5. Each log line contains request_id AND path fields (middleware composing).
6. context_var composition: a second bind (simulating a later module doing
   logger.bind(repo_id=...)) co-exists with request_id on the same log line.

Usage
-----
    # Terminal 1 — start the server, capture JSON logs to a file:
    uvicorn app.main:app --port 8000 > /tmp/logs.json 2>&1

    # Terminal 2 — run this script:
    python validate_module2_live.py

Or run it programmatically (starts/stops the server itself):
    python validate_module2_live.py --self-hosted
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def get(path: str) -> tuple[int, dict, dict]:
    """Return (status_code, response_headers, body_dict)."""
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read())
        headers = dict(resp.headers)
    return resp.status, headers, body


def validate_against_running_server(log_file: Path) -> None:
    ids: list[str] = []

    print("── Test 1-3: /health response shape & distinct IDs ──────────────")
    for i in range(3):
        status, headers, body = get("/health")
        assert status == 200, f"Expected 200, got {status}"
        assert body.get("status") == "ok", f"Unexpected body: {body}"
        rid = headers.get("X-Request-ID") or headers.get("x-request-id")
        assert rid, "X-Request-ID header missing from response"
        ids.append(rid)
        print(f"  request {i+1}: id={rid}  status={status}  body={body}")

    assert len(set(ids)) == 3, f"Request IDs are not distinct: {ids}"
    print("  [PASS] 3 requests, 3 distinct X-Request-ID values")

    print()
    print("── Test 4-5: stdout log JSON validity & required fields ─────────")
    time.sleep(0.2)  # let the server flush stdout
    lines = [l for l in log_file.read_text().splitlines() if l.strip().startswith("{")]
    assert lines, "No JSON log lines found in server stdout"
    for line in lines:
        obj = json.loads(line)  # raises if not valid JSON
        assert "request_id" in obj, f"'request_id' missing from log line: {line}"
        assert "path" in obj, f"'path' missing from log line: {line}"
    print(f"  [PASS] {len(lines)} JSON log lines found, all contain request_id + path")

    print()
    print("── Test 6: context-var composition (simulated Module 3 bind) ────")
    # This is a code-level unit test — we can run it in-process.
    os.environ.setdefault("LLM_PROVIDER", "ollama")
    from app.observability.logging_config import configure_logging
    import structlog
    configure_logging()

    captured: list[str] = []

    class _Capture:
        def msg(self, message): captured.append(message)
        log = msg  # structlog calls .msg()

    structlog.configure(logger_factory=lambda *a: _Capture())

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-abc-123", path="/ingest")
    log = structlog.get_logger().bind(repo_id="owner/repo", component="ingestion")
    log.info("clone_started", size_mb=42)

    assert captured, "No log output captured"
    record = json.loads(captured[0]) if captured[0].startswith("{") else {}
    # The composed record should carry ALL context — both middleware's request_id
    # and the ingestion module's repo_id — on a single line.
    assert record.get("request_id") == "req-abc-123", record
    assert record.get("repo_id") == "owner/repo", record
    assert record.get("component") == "ingestion", record
    print("  [PASS] request_id + repo_id + component all present on one log line")

    print()
    print("ALL LIVE VALIDATION CHECKS PASSED")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--self-hosted",
        action="store_true",
        help="Launch uvicorn in a subprocess, run tests, then shut it down.",
    )
    args = parser.parse_args()

    if args.self_hosted:
        log_path = Path(tempfile.mktemp(suffix=".log"))
        print(f"Starting uvicorn, logging to {log_path}")
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000"],
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
        )
        time.sleep(2)  # wait for startup
        try:
            validate_against_running_server(log_path)
        finally:
            proc.terminate()
            proc.wait()
    else:
        # Assume server is already running; use a dummy log file for the JSON check.
        log_path = Path(tempfile.mktemp(suffix=".log"))
        print("Assuming uvicorn is already running on :8000")
        print("(Use --self-hosted to auto-start/stop the server)")
        print()
        # For the log-content checks, redirect server stdout yourself and pass the path:
        validate_against_running_server(log_path)


if __name__ == "__main__":
    main()
