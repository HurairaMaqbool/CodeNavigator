#!/usr/bin/env python3
"""Systematic ingestion pipeline audit — Phases 2 & 3."""
from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

JOB_ID = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
REPO_URL = "https://github.com/psf/requests"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def report(phase: str, name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {phase} — {name}"
    if detail:
        line += f": {detail}"
    print(line, flush=True)


def phase2_module_tests() -> bool:
    all_ok = True
    clone_path: Path | None = None
    files = []
    parsed_files = []
    chunks = []

    # 1 locking
    try:
        from app.ingestion.locking import lock_manager
        from app.ingestion.metadata_store import metadata_store

        test_id = "audit-lock-test"
        metadata_store.mark_pending(test_id, REPO_URL, "HEAD")
        res = lock_manager.try_acquire(test_id, metadata_store)
        assert res.acquired, "lock not acquired"
        try:
            raise RuntimeError("simulated failure")
        except RuntimeError:
            pass
        finally:
            lock_manager.release(test_id)
        report("PHASE2", "locking.py", True, "acquire/release on exception OK")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "locking.py", False, f"{exc}\n{traceback.format_exc()}")

    # 2 clone
    try:
        from app.ingestion.clone import clone_repo

        clone_res = clone_repo(REPO_URL, None)
        clone_path = clone_res.clone_path
        assert clone_path.is_dir(), "clone path missing"
        assert clone_res.commit_hash and len(clone_res.commit_hash) == 40
        report(
            "PHASE2",
            "clone.py",
            True,
            f"path={clone_path} commit={clone_res.commit_hash[:12]}…",
        )
    except Exception as exc:
        all_ok = False
        report("PHASE2", "clone.py", False, f"{exc}\n{traceback.format_exc()}")

    # 3 file_filter
    try:
        from app.ingestion.file_filter import filter_repo_files

        if clone_path is None:
            raise RuntimeError("clone skipped")
        files = filter_repo_files(clone_path, repo_id=JOB_ID)
        assert len(files) > 0, "zero files after filter"
        report("PHASE2", "file_filter.py", True, f"{len(files)} files")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "file_filter.py", False, f"{exc}\n{traceback.format_exc()}")

    # 4 metadata_store
    try:
        from app.ingestion.metadata_store import Stage, metadata_store

        metadata_store.mark_pending("audit-meta", REPO_URL, "HEAD")
        metadata_store.update("audit-meta", Stage.PARSING, progress="audit test")
        meta = metadata_store.get("audit-meta")
        assert meta and meta.sync_status == "parsing"
        report("PHASE2", "metadata_store.py", True, f"sync_status={meta.sync_status}")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "metadata_store.py", False, f"{exc}\n{traceback.format_exc()}")

    # 5 tree_sitter_parser
    try:
        from app.ingestion.file_filter import safe_decode
        from app.parsing.tree_sitter_parser import parse_file

        if not files:
            raise RuntimeError("no files to parse")
        sample = files[:5]
        ok_n = 0
        for f in sample:
            text, err = safe_decode(Path(f.path))
            if err or not text:
                continue
            parsed = parse_file(str(f.path), text, f.language)
            if parsed:
                parsed.file_path = f.display_path
                parsed_files.append(parsed)
                ok_n += 1
        assert ok_n > 0, "no successful parses in sample"
        report("PHASE2", "tree_sitter_parser.py", True, f"{ok_n}/{len(sample)} sample files parsed")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "tree_sitter_parser.py", False, f"{exc}\n{traceback.format_exc()}")

    # 6 chunker
    try:
        from app.ingestion.file_filter import safe_decode
        from app.parsing.chunker import chunk_all_files

        if not parsed_files:
            raise RuntimeError("no parsed files")
        contents = {}
        file_records = {}
        for f in files[:20]:
            text, err = safe_decode(Path(f.path))
            if err or not text:
                continue
            contents[f.display_path] = text
            file_records[f.display_path] = (str(f.path), f.display_path, f.normalized_path)
        chunks = chunk_all_files(parsed_files, contents, file_records)
        assert len(chunks) > 0, "zero chunks"
        report("PHASE2", "chunker.py", True, f"{len(chunks)} chunks")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "chunker.py", False, f"{exc}\n{traceback.format_exc()}")

    # 7 embeddings
    try:
        from app.retrieval.embeddings import embed_chunks

        if not chunks:
            raise RuntimeError("no chunks")
        sample_chunks = chunks[:10]
        embed_chunks(sample_chunks)
        vecs = [getattr(c, "vector", None) for c in sample_chunks]
        assert all(v is not None for v in vecs), "missing vectors"
        report("PHASE2", "embeddings.py", True, f"{len(sample_chunks)} vectors dim={len(vecs[0])}")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "embeddings.py", False, f"{exc}\n{traceback.format_exc()}")

    # 8 vector_store
    try:
        from app.retrieval.embeddings import embed_chunks
        from app.retrieval.vector_store import get_collection, store_chunks, query
        from app.retrieval.embeddings import embed

        if not chunks:
            raise RuntimeError("no chunks")
        test_chunks = chunks[:15]
        embed_chunks(test_chunks)
        store_chunks(JOB_ID, test_chunks, force_reindex=False)
        col = get_collection(JOB_ID)
        assert col is not None and col.count() > 0
        qv = embed("Session send request")
        hits = query(JOB_ID, qv, top_k=3)
        assert len(hits) > 0
        report("PHASE2", "vector_store.py", True, f"count={col.count()} hits={len(hits)}")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "vector_store.py", False, f"{exc}\n{traceback.format_exc()}")

    # 9 bm25
    try:
        from app.retrieval.bm25_store import build_bm25_index, search_bm25

        if not chunks:
            raise RuntimeError("no chunks")
        build_bm25_index(JOB_ID, chunks[:50])
        hits = search_bm25(JOB_ID, "Session send", top_n=3)
        assert len(hits) > 0
        report("PHASE2", "bm25_store.py", True, f"{len(hits)} hits")
    except Exception as exc:
        all_ok = False
        report("PHASE2", "bm25_store.py", False, f"{exc}\n{traceback.format_exc()}")

    return all_ok


def phase3_e2e(force_reindex: bool = True) -> bool:
    import requests
    from app.config import settings

    base = "http://localhost:8000"
    headers = {"X-API-Key": settings.API_KEY, "Content-Type": "application/json"}

    print(f"\n=== PHASE 3 E2E ingest force_reindex={force_reindex} ===", flush=True)
    try:
        r = requests.post(
            f"{base}/ingest",
            headers=headers,
            json={"repo_url": REPO_URL, "force_reindex": force_reindex},
            timeout=120,
        )
        print(f"[{_ts()}] POST /ingest -> {r.status_code} {r.text[:200]}", flush=True)
        if r.status_code not in (200, 202):
            return False
        job_id = r.json().get("job_id", JOB_ID)
    except Exception as exc:
        report("PHASE3", "POST /ingest", False, str(exc))
        return False

    deadline = time.time() + 600
    last_stage = None
    while time.time() < deadline:
        try:
            s = requests.get(f"{base}/status/{job_id}", headers=headers, timeout=30)
            body = s.json()
        except Exception as exc:
            print(f"[{_ts()}] status poll error: {exc}", flush=True)
            time.sleep(3)
            continue

        stage = body.get("sync_status")
        status = body.get("status")
        files = body.get("files_parsed", 0)
        chunks = body.get("chunks_created", 0)
        if stage != last_stage:
            print(
                f"[{_ts()}] stage={stage} api_status={status} files={files} chunks={chunks}",
                flush=True,
            )
            last_stage = stage

        if status == "ready" or stage == "synced":
            ok = files > 0 and chunks > 0
            report(
                "PHASE3",
                "E2E SYNCED",
                ok,
                json.dumps(body),
            )
            return ok
        if status == "failed" or stage == "failed":
            report("PHASE3", "E2E FAILED", False, json.dumps(body))
            return False
        time.sleep(3)

    report("PHASE3", "E2E timeout", False, f"last_stage={last_stage}")
    return False


if __name__ == "__main__":
    print("=== PHASE 1 (read metadata on disk) ===")
    meta_path = PROJECT_ROOT / "data" / "repos" / JOB_ID / "metadata.json"
    if meta_path.exists():
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        print(json.dumps(raw, indent=2))
    else:
        print("metadata.json missing")

    p2 = phase2_module_tests()
    p3 = phase3_e2e(force_reindex=True) if p2 else False
    sys.exit(0 if (p2 and p3) else 1)
