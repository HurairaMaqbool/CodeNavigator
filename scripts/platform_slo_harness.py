#!/usr/bin/env python3
# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
scripts/platform_slo_harness.py
-------------------------------
5-run Platform module measurements (usage, billing, audit, API keys).

Usage:
  python scripts/platform_slo_harness.py [--runs 5] [--base-url http://127.0.0.1:8000]
"""
from __future__ import annotations

import argparse
import http.client
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "eval_results" / "platform_slo_harness_latest.json"


class _KeepAliveSession:
    """Reuse TCP connection for accurate latency measurement."""

    def __init__(self, base_url: str, api_key: str):
        parsed = urllib.parse.urlparse(base_url)
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._api_key = api_key
        self._conn = http.client.HTTPConnection(self._host, self._port, timeout=15)

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> tuple[float, dict | list | None, str | None]:
        t0 = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        payload = json.dumps(body).encode() if body is not None else None
        try:
            self._conn.request(method, path, body=payload, headers=headers)
            resp = self._conn.getresponse()
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            err = None if 200 <= resp.status < 300 else f"HTTP {resp.status}: {raw[:200]}"
        except Exception as exc:
            parsed = None
            err = str(exc)
        ms = (time.perf_counter() - t0) * 1000
        return ms, parsed, err

    def close(self) -> None:
        self._conn.close()


def _request(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[float, dict | list | None, str | None]:
    t0 = time.perf_counter()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            parsed = json.loads(raw) if raw else {}
            err = None
    except urllib.error.HTTPError as exc:
        parsed = None
        err = f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:
        parsed = None
        err = str(exc)
    ms = (time.perf_counter() - t0) * 1000
    return ms, parsed, err


def measure_endpoint(
    base_url: str,
    name: str,
    method: str,
    path: str,
    api_key: str,
    runs: int,
    body: dict | None = None,
) -> dict:
    latencies: list[float] = []
    oks: list[bool] = []
    for _ in range(runs):
        session = _KeepAliveSession(base_url, api_key)
        try:
            ms, _, err = session.request(method, path, body)
        finally:
            session.close()
        latencies.append(ms)
        oks.append(err is None)
    return {
        "component": name,
        "runs": runs,
        "ok_rate": f"{sum(oks)}/{runs}",
        "consistent": len(set(oks)) == 1 and all(oks),
        "latency_ms": {"p50": statistics.median(latencies), "max": max(latencies)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--latency-budget-ms", type=float, default=500.0)
    parser.add_argument("--api-key", default="dev-secret-key")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    key = args.api_key
    runs = args.runs

    results = [
        measure_endpoint(base, "Usage summary", "GET", "/platform/usage", key, runs),
        measure_endpoint(base, "Billing subscription", "GET", "/billing/subscription", key, runs),
        measure_endpoint(base, "Audit trail", "GET", "/platform/audit?limit=50", key, runs),
        measure_endpoint(base, "API key list", "GET", "/platform/api-keys", key, runs),
        measure_endpoint(base, "GitHub installations", "GET", "/platform/github/installations", key, runs),
        measure_endpoint(base, "Repository list", "GET", "/platform/repos", key, runs),
        measure_endpoint(base, "Billing plans (public)", "GET", "/billing/plans", "", runs),
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    latency_ok = all(
        r.get("latency_ms", {}).get("p50", 9999) <= args.latency_budget_ms
        for r in results
        if "skipped" not in r
    )
    payload = {"runs": runs, "latency_budget_ms": args.latency_budget_ms, "latency_ok": latency_ok, "results": results}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    all_ok = all(r.get("consistent") for r in results if "skipped" not in r)
    return 0 if all_ok and latency_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
