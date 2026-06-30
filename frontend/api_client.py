"""
frontend/api_client.py
----------------------
Thin HTTP wrapper around the FastAPI backend (Module 12).
No business logic, just request/response typing and error handling.
"""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

import requests

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("API_KEY", "dev-secret-key")

def _get_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY} if API_KEY else {}

class APIError(Exception):
    def __init__(self, status_code: int, message: str, raw_response: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.raw_response = raw_response

def _handle_response(resp: requests.Response) -> dict[str, Any]:
    if 200 <= resp.status_code < 300:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}
            
    try:
        err = resp.json()
        msg = err.get("detail", err.get("error", resp.text))
    except Exception:
        msg = resp.text
        
    raise APIError(resp.status_code, str(msg), resp.text)

def ingest(repo_url: str, ref: str | None = None, force_reindex: bool = False) -> dict[str, Any]:
    payload = {"repo_url": repo_url, "force_reindex": force_reindex}
    if ref:
        payload["ref"] = ref
    # Ingest returns 202 quickly; clone/embed run async in worker/background.
    res = requests.post(
        f"{API_BASE_URL}/ingest",
        json=payload,
        headers=_get_headers(),
        timeout=(10, 90),
    )
    return _handle_response(res)


def get_status(job_id: str) -> dict[str, Any]:
    res = requests.get(f"{API_BASE_URL}/status/{job_id}", headers=_get_headers(), timeout=10)
    return _handle_response(res)

def chat(repo_id: str, question: str, session_id: str | None = None) -> dict[str, Any]:
    payload = {"repo_id": repo_id, "question": question}
    if session_id:
        payload["session_id"] = session_id
    res = requests.post(f"{API_BASE_URL}/chat", json=payload, headers=_get_headers(), timeout=300)
    return _handle_response(res)

def get_diagram(repo_id: str, function_name: str, depth: int = 2) -> dict[str, Any]:
    fn = urllib.parse.quote(function_name, safe="")
    res = requests.get(
        f"{API_BASE_URL}/diagram/{repo_id}/{fn}",
        params={"depth": depth},
        headers=_get_headers(),
        timeout=30,
    )
    return _handle_response(res)

def get_eval_health(repo_id: str, probe_agent: bool = False) -> dict[str, Any]:
    """Check whether the repo index and retrieval pipeline are ready for evaluation."""
    res = requests.get(
        f"{API_BASE_URL}/eval/health/{repo_id}",
        params={"probe_agent": str(probe_agent).lower()},
        headers=_get_headers(),
        timeout=120,
    )
    return _handle_response(res)


def start_eval(repo_id: str | None = None) -> dict[str, Any]:
    """Start an async RAGAS evaluation run. Returns immediately with a job_id."""
    params = {"repo_id": repo_id} if repo_id else None
    res = requests.post(
        f"{API_BASE_URL}/eval/run",
        params=params,
        headers=_get_headers(),
        timeout=10,
    )
    return _handle_response(res)


def get_eval_status(job_id: str) -> dict[str, Any]:
    """Poll the status of an async eval job. Status: queued | running | done | error"""
    res = requests.get(
        f"{API_BASE_URL}/eval/status/{job_id}", headers=_get_headers(), timeout=15
    )
    return _handle_response(res)

def run_eval() -> dict[str, Any]:
    """Deprecated: kept for backward compatibility. Use start_eval() + get_eval_status() instead."""
    res = requests.get(f"{API_BASE_URL}/eval/run", headers=_get_headers(), timeout=30)
    return _handle_response(res)

def get_eval_history() -> list[dict[str, Any]]:
    """Return all historical eval run records from the backend."""
    res = requests.get(f"{API_BASE_URL}/eval/history", headers=_get_headers(), timeout=30)
    data = _handle_response(res)
    # The endpoint returns a list; _handle_response may wrap non-dict payloads
    if isinstance(data, list):
        return data
    return data.get("raw", []) if isinstance(data, dict) else []

def compare_eval_runs(baseline_version: str, candidate_version: str, tolerance: float = 0.05) -> dict[str, Any]:
    """Compare two historical eval runs via the backend comparison endpoint."""
    payload = {
        "baseline_version": baseline_version,
        "candidate_version": candidate_version,
        "tolerance": tolerance,
    }
    res = requests.post(
        f"{API_BASE_URL}/eval/compare", json=payload, headers=_get_headers(), timeout=30
    )
    return _handle_response(res)


def get_golden_status() -> dict[str, Any]:
    """Get the status of the Golden Set CI test run."""
    res = requests.get(f"{API_BASE_URL}/eval/golden-status", headers=_get_headers(), timeout=10)
    return _handle_response(res)


def start_golden_run() -> dict[str, Any]:
    """Trigger async golden set CI; poll with get_eval_status(job_id)."""
    res = requests.post(f"{API_BASE_URL}/eval/golden/run", headers=_get_headers(), timeout=15)
    return _handle_response(res)


def get_platform_usage() -> dict[str, Any]:
    res = requests.get(f"{API_BASE_URL}/platform/usage", headers=_get_headers(), timeout=10)
    return _handle_response(res)


def get_billing_subscription() -> dict[str, Any]:
    res = requests.get(f"{API_BASE_URL}/billing/subscription", headers=_get_headers(), timeout=10)
    return _handle_response(res)


def get_platform_audit(limit: int = 50) -> list[dict[str, Any]]:
    res = requests.get(f"{API_BASE_URL}/platform/audit?limit={limit}", headers=_get_headers(), timeout=10)
    return _handle_response(res)

