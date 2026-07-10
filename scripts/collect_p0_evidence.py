#!/usr/bin/env python3
"""Phase 1 evidence collector for P0 false-block on /chat."""
from __future__ import annotations

import json
import re
from pathlib import Path

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
QUESTION = "How request parameters are validated and processed."
COMMIT_FROM_JOB = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "repos"


def load_raw(repo_id: str) -> dict | None:
    p = DATA / repo_id / "metadata.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def alias_for(job_id: str) -> str | None:
    p = DATA / job_id / "alias.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8")).get("real_repo_id")


def scan_logs(repo_id: str, limit: int = 50) -> list[str]:
    patterns = (
        "ingestion_task",
        "locking",
        "metadata_store",
        "sync_status_transition",
        "mark_synced",
        "mark_failed",
    )
    hits: list[tuple[str, str]] = []
    log_dirs = [ROOT / "logs", ROOT / "data" / "logs", Path.home() / ".cursor" / "projects"]
    for base in log_dirs:
        if not base.exists():
            continue
        for path in base.rglob("*.log"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if repo_id not in line:
                    continue
                if not any(p in line for p in patterns):
                    continue
                hits.append((line, str(path)))
    hits.sort(key=lambda x: x[0])
    return [f"{line}  [{path}]" for line, path in hits[-limit:]]


def chroma_count(repo_id: str) -> int | None:
    try:
        from app.retrieval.vector_store import get_collection

        col = get_collection(repo_id)
        return col.count() if col else 0
    except Exception as exc:
        return None if "No module" in str(type(exc).__name__) else -1


def bm25_count(repo_id: str) -> int | None:
    try:
        from app.retrieval.bm25_store import load_bm25_index

        idx = load_bm25_index(repo_id)
        if idx is None:
            return 0
        return len(getattr(idx, "doc_ids", []) or getattr(idx, "corpus", []) or [])
    except Exception:
        return None


def main() -> None:
    print("=" * 72)
    print("PHASE 1 — P0 /chat false-block evidence")
    print("=" * 72)
    print(f"\nFrontend /chat payload (from screenshot):")
    print(f"  repo_id:    {JOB_ID}")
    print(f"  question:   {QUESTION!r}")
    print(f"  commit_hash: (not sent by frontend — resolved server-side)")

    asset = alias_for(JOB_ID)
    print(f"\nAlias: job_id -> asset_repo_id = {asset}")

    for label, rid in [("job_id", JOB_ID), ("asset_repo_id", asset)]:
        if not rid:
            continue
        raw = load_raw(rid)
        print(f"\n--- metadata_store raw record [{label}] {rid} ---")
        if raw is None:
            print("  (missing)")
            continue
        keys = (
            "sync_status",
            "last_stage",
            "files_parsed",
            "file_count",
            "chunks_created",
            "error_reason",
            "commit_hash",
            "sync_started_at",
            "cloned_at",
            "parsing_progress",
        )
        for k in keys:
            if k in raw:
                print(f"  {k}: {raw[k]}")

    print("\n--- Chroma / BM25 (independent of metadata) ---")
    for rid in filter(None, [JOB_ID, asset]):
        c = chroma_count(rid)
        b = bm25_count(rid)
        print(f"  {rid[:16]}... chroma_chunks={c} bm25_docs={b}")

    print("\n--- Log timeline (last 50 matching lines) ---")
    timeline = scan_logs(JOB_ID) + scan_logs(asset or "")
    timeline = sorted(set(timeline))[-50:]
    if timeline:
        for line in timeline:
            print(line)
    else:
        print("  (no structured log files found — transitions visible in metadata.json timestamps)")

    job_raw = load_raw(JOB_ID) or {}
    asset_raw = load_raw(asset) if asset else {}
    print("\n--- Root cause classification ---")
    job_synced = job_raw.get("sync_status") == "synced"
    asset_indexing = asset_raw.get("sync_status") == "indexing"
    if job_synced and asset_indexing:
        print("PRIMARY: (b) stale checkpoint on asset_repo_id + (e) read-path bug")
        print("  Evidence: job_id metadata synced with chunks; asset alias stuck at indexing;")
        print("  /chat router gated on job_id (passed) but agent INTAKE gated on asset_repo_id.")
    elif asset_raw.get("sync_status") in ("pending", "cloning", "parsing", "indexing"):
        print("Could be (a) genuinely indexing — verify lock + sync_started_at age")
    else:
        print("See metadata records above for classification")


if __name__ == "__main__":
    main()
