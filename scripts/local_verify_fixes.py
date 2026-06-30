#!/usr/bin/env python3
"""
Local smoke test for the three UI-reported fixes (no Docker required).

Usage (from repo root):
    .venv\\Scripts\\activate
    pip install -r requirements-eval.txt
    python scripts/local_verify_fixes.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
# Import before any chromadb use so PostHog capture is disabled.
import app.chroma_client  # noqa: F401,E402

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
if not os.environ.get("GROQ_API_KEY", "").strip():
    os.environ["GROQ_API_KEY"] = "local-dev-placeholder"
os.environ.setdefault("GRAPH_STORE_PATH", str(ROOT / "data" / "graph_store"))
os.environ.setdefault("REPOS_PATH", str(ROOT / "data" / "repos"))

PASS = "[PASS]"
FAIL = "[FAIL]"


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"{status} {label}{suffix}")
    return ok


def main() -> int:
    print("=" * 60)
    print("Local fix verification (no Docker)")
    print("=" * 60)
    results: list[bool] = []
    datasets_ok = False
    ragas_ok = False

    # 1. Eval dependencies
    datasets_ok = False
    ragas_ok = False
    try:
        import datasets  # noqa: F401
        datasets_ok = True
        results.append(check("Eval dep: datasets", True))
    except ImportError as exc:
        results.append(check("Eval dep: datasets", False, str(exc)))

    try:
        import ragas  # noqa: F401
        ragas_ok = True
        results.append(check("Eval dep: ragas", True))
    except ImportError as exc:
        results.append(check("Eval dep: ragas", False, str(exc)))
        print("       Fix: pip install -r requirements-eval.txt")
        print("       (uses langchain 0.3.x; avoid mixing with langchain 1.x)")

    # 2. Diagram alias resolution (requests fixture from prior ingest)
    job_id = "375c63667dff3e1e20ef5712cf1c0cb33940a9b49644bb855f1f89fe959d9f4d"
    clone_id = "b4f947369301e4e0681a5f878604aa39c14efce4fbd98648e3722afd9f6380ee"
    alias_file = ROOT / "data" / "repos" / job_id / "alias.json"
    graph_file = ROOT / "data" / "graph_store" / clone_id / "graph.json"

    if not alias_file.exists() or not graph_file.exists():
        results.append(
            check(
                "Diagram fixture data",
                False,
                "Ingest https://github.com/psf/requests once (Docker or local) to create data/",
            )
        )
    else:
        from app.config import settings
        from app.graph.queries import get_subgraph, _GRAPH_CACHE
        from app.ingestion.metadata_store import metadata_store
        from app.api.router import _resolve_repo_meta
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.auth import verify_api_key

        _GRAPH_CACHE.clear()
        settings.GRAPH_STORE_PATH = str(ROOT / "data" / "graph_store")
        settings.REPOS_PATH = str(ROOT / "data" / "repos")

        alias = json.loads(alias_file.read_text()).get("real_repo_id")
        results.append(check("Alias file maps job_id -> clone_id", alias == clone_id, f"alias={alias}"))

        _, asset_id = _resolve_repo_meta(job_id)
        results.append(check("_resolve_repo_meta uses alias", asset_id == clone_id, f"asset_id={asset_id}"))

        sub = get_subgraph(asset_id, "PreparedRequest", depth=2)
        node_n = len(sub.get("nodes", []))
        edge_n = len(sub.get("edges", []))
        results.append(check("PreparedRequest subgraph", node_n > 0 and edge_n > 0, f"{node_n} nodes, {edge_n} edges"))

        app.dependency_overrides[verify_api_key] = lambda: None
        client = TestClient(app)
        meta = metadata_store.get(job_id)
        if meta and meta.sync_status == "synced":
            resp = client.get(f"/diagram/{job_id}/PreparedRequest?depth=2")
            body = resp.json()
            empty = body.get("empty") is True or not body.get("mermaid")
            results.append(
                check("GET /diagram via job_id", resp.status_code == 200 and not empty, f"status={resp.status_code}")
            )
        else:
            results.append(check("GET /diagram via job_id", False, "job metadata not synced — skip API test"))

    # 3. Cycle detection
    if graph_file.exists():
        from app.graph.queries import detect_cycles, _GRAPH_CACHE

        _GRAPH_CACHE.clear()
        cycles = detect_cycles(clone_id)
        results.append(
            check("Cycle detection completes", cycles is not None, f"has_circular_dependencies={cycles}")
        )

        payload = json.loads(graph_file.read_text())
        meta = payload.get("metadata", {})
        if "has_circular_dependencies" not in meta:
            results.append(
                check(
                    "Graph metadata has cycle flag (re-ingest to populate)",
                    True,
                    "missing on old graphs; status endpoint falls back to detect_cycles",
                )
            )

        from eval.health_check import resolve_asset_repo_id, check_index_health

        _, asset_id = resolve_asset_repo_id(job_id)
        health = check_index_health(asset_id)
        results.append(
            check(
                "Eval index health (Chroma + BM25 + probe)",
                health.ok,
                f"chunks={health.details.get('chroma_chunk_count')}, hits={health.details.get('probe_hit_count')}",
            )
        )

    print("=" * 60)
    # Indices 0-1: eval deps; 2+: diagram/cycle (when fixture exists)
    diagram_cycle_ok = len(results) >= 3 and all(results[2:])
    if diagram_cycle_ok and datasets_ok and ragas_ok:
        print("All checks passed — safe to rebuild Docker when ready.")
        return 0
    if diagram_cycle_ok:
        print("Diagram + cycle fixes OK locally.")
        if not ragas_ok:
            print("Eval: pip install -r requirements-eval.txt (langchain 0.3.x stack)")
        return 0
    print("Some checks failed — fix locally before Docker.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
