# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/jobs/eval_job_store.py
--------------------------
Eval job state: Redis (primary) + disk fallback + in-process cache.

Survives API restarts and is visible across Gunicorn workers when Redis is up.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.config import settings
from app.redis_client import get_redis

from app.paths import data_path

_EVAL_JOBS_DIR = data_path("eval_jobs")
_REDIS_PREFIX = "eval:job:"
_MEMORY: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _persist_disk(job_id: str, job: dict[str, Any]) -> None:
    try:
        _EVAL_JOBS_DIR.mkdir(parents=True, exist_ok=True)
        path = _EVAL_JOBS_DIR / f"{job_id}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(job, fh, default=str)
    except Exception:
        pass


def _load_disk(job_id: str) -> dict[str, Any] | None:
    path = _EVAL_JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _persist_redis(job_id: str, job: dict[str, Any]) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(
            f"{_REDIS_PREFIX}{job_id}",
            settings.REDIS_EVAL_JOB_TTL_SECONDS,
            json.dumps(job, default=str),
        )
    except Exception:
        pass


def _load_redis(job_id: str) -> dict[str, Any] | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(f"{_REDIS_PREFIX}{job_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def set_eval_job(job_id: str, **updates: Any) -> dict[str, Any]:
    with _LOCK:
        job = _MEMORY.get(job_id) or _load_redis(job_id) or _load_disk(job_id) or {}
        job.update(updates)
        _MEMORY[job_id] = job
    _persist_disk(job_id, job)
    _persist_redis(job_id, job)
    return job


def get_eval_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        if job_id in _MEMORY:
            return _MEMORY[job_id]
    job = _load_redis(job_id)
    if job is not None:
        with _LOCK:
            _MEMORY[job_id] = job
        return job
    job = _load_disk(job_id)
    if job is not None:
        with _LOCK:
            _MEMORY[job_id] = job
        _persist_redis(job_id, job)
    return job
