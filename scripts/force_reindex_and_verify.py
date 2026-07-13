#!/usr/bin/env python3
# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
Force re-index psf/requests and verify index integrity + eval precheck.

Calls the ingestion pipeline directly (no HTTP/Celery required).

Usage:
  python scripts/force_reindex_and_verify.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPO_URL = "https://github.com/psf/requests"
REF = "main"
# Frontend / eval harness canonical job id (may alias to asset repo id after clone).
EVAL_JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"


def main() -> int:
    from app.ingestion.locking import lock_manager
    from app.ingestion.metadata_store import metadata_store
    from app.ingestion.pipeline import run_ingestion_sync
    from eval.health_check import run_full_eval_precheck

    job_id = EVAL_JOB_ID
    print(f"Job ID: {job_id}")
    print("Starting force reindex for psf/requests …")

    lock = lock_manager.try_acquire(job_id, metadata_store)
    if not lock.acquired:
        print("Ingest already running — polling until synced or failed …")
        deadline = time.time() + 900
        while time.time() < deadline:
            meta = metadata_store.get(job_id)
            if meta and meta.sync_status == "synced":
                break
            if meta and meta.sync_status == "failed":
                print("Ingest failed:", meta.error_reason)
                return 1
            time.sleep(5)
    else:
        metadata_store.mark_pending(job_id, REPO_URL, REF)
        ok = run_ingestion_sync(REPO_URL, REF, True, job_id)
        if not ok:
            meta = metadata_store.get(job_id)
            print("Ingest failed:", getattr(meta, "error_reason", "unknown"))
            return 1

    pre = run_full_eval_precheck(EVAL_JOB_ID, include_agent_probe=False)
    report = {
        "job_id": EVAL_JOB_ID,
        "precheck_ok": pre.ok,
        "errors": pre.errors,
        "integrity_ok": pre.details.get("ok"),
        "chroma_chunks": pre.details.get("chroma_chunks"),
        "metadata_chunks": pre.details.get("metadata_chunks_created")
        or pre.details.get("chunks_created"),
        "bm25_chunks": pre.details.get("bm25_chunks"),
        "details": pre.details,
    }
    out = ROOT / "eval_results" / "reindex_verify_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if pre.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
