# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/api/router.py
-----------------
FastAPI routers mapping to Module 12 requirements.
"""
from __future__ import annotations

import threading
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass
import json

def _validate_repo_id(repo_id: str) -> None:
    if not repo_id or not re.match(r"^(?:[a-fA-F0-9]{64}|public)$", repo_id):
        raise HTTPException(status_code=400, detail="Invalid repo_id format")

def _validate_eval_job_id(job_id: str) -> None:
    if not job_id or not re.match(r"^[a-fA-F0-9]{32}$", job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl, Field

from app.config import settings
from app.observability.logging_config import logger
from app.api.auth import verify_api_key

# Ingestion
from app.ingestion.clone import (
    repo_id_for, clone_repo,  # noqa: F401
    IngestionError, InvalidURLError, RepoNotFoundError, PrivateRepoError, NetworkTimeoutError, RepoTooLargeError
)
from app.ingestion.metadata_store import metadata_store
from app.ingestion.locking import lock_manager
from app.ingestion.file_filter import safe_decode, filter_repo_files  # noqa: F401
from app.parsing.chunker import chunk_all_files
from app.parsing.tree_sitter_parser import parse_file
from app.retrieval.vector_store import store_chunks
from app.retrieval.bm25_store import build_bm25_index
from app.graph.builder import build_graph
from app.graph.queries import get_subgraph

# Chat & Diagram
from app.agent.loop import run
from app.agent.llm_client import RateLimitError
from app.diagrams.mermaid_generator import graph_to_mermaid, generate_mermaid
from app.api.rate_limiter import limiter

router = APIRouter()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    repo_url: HttpUrl
    ref: str | None = None
    force_reindex: bool = False

class ChatRequest(BaseModel):
    repo_id: str
    question: str = Field(min_length=5, max_length=settings.MAX_QUESTION_LENGTH)
    session_id: str | None = Field(default=None, description="Optional session ID for multi-turn chat memory")

class ChatSource(BaseModel):
    file_path: str
    function_name: str
    start_line: int
    end_line: int

class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = []
    confidence_score: float = 0.0
    gated: bool = False

class DiagramRequest(BaseModel):
    repo_id: str
    entry_point: str
    direction: str = "both"  # callers | callees | both

class DiagramResponse(BaseModel):
    mermaid_markdown: str

class OnboardingPathRequest(BaseModel):
    repo_id: str
    role: str
    experience_level: str

class OnboardingPathStep(BaseModel):
    file_path: str
    why_it_matters: str
    suggested_order: int
    related_functions: list[str]

class OnboardingPathResponse(BaseModel):
    onboarding_path: list[OnboardingPathStep]

@dataclass
class IngestJobResponse:
    job_id: str
    status: str

# ---------------------------------------------------------------------------
# Health & Readiness Check
# ---------------------------------------------------------------------------
@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/ready")
def readiness():
    # Basic readiness check - can be expanded to check DB connections
    try:
        from app.retrieval.vector_store import _get_client
        _get_client()
        chroma_ok = True
    except Exception:
        chroma_ok = False

    from app.redis_client import ping_redis
    redis_ok = ping_redis()

    from app.platform.db.postgres import check_connection
    from app.platform.db.connection import postgres_enabled
    postgres_ok = check_connection() if postgres_enabled() else "not_configured"
        
    checks = {
        "chroma": chroma_ok,
        "redis": redis_ok if redis_ok else "unavailable",
        "postgres": postgres_ok,
    }
    all_ok = chroma_ok
    
    return Response(
        status_code=200 if all_ok else 503,
        content=json.dumps({"status": "ready" if all_ok else "degraded", **checks}),
        media_type="application/json"
    )

# ---------------------------------------------------------------------------
# Ingestion Orchestration
# ---------------------------------------------------------------------------

from app.ingestion.metadata_store import Stage

# Intermediate pipeline stages — single source: Stage.in_progress_values()
_INGEST_IN_PROGRESS_STATUSES = Stage.in_progress_values()


def _celery_workers_available() -> bool:
    """True when at least one Celery worker responds to a control ping."""
    try:
        from app.tasks.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=1.0)
        ping = inspector.ping()
        return bool(ping)
    except Exception as exc:
        logger.debug("celery_worker_probe_failed", error=str(exc))
        return False


def _ingest_progress_counts(meta: Any, asset_repo_id: str) -> tuple[int, int]:
    """Resolve files/chunks for /status from metadata with vector-store fallback."""
    from app.ingestion.progress_counts import ingest_progress_counts

    return ingest_progress_counts(meta, asset_repo_id, job_id=getattr(meta, "repo_id", None))


def _api_status_for_sync(sync_status: str) -> str:
    """Map metadata sync_status → API status field consumed by frontend polling."""
    if Stage.is_failed(sync_status):
        return Stage.FAILED.value
    if Stage.is_synced(sync_status):
        return "ready"
    if Stage.is_in_progress(sync_status):
        return "processing"
    logger.warning("unknown_sync_status_treated_as_processing", sync_status=sync_status)
    return "processing"


def _raise_for_ingestion_error(exc: IngestionError) -> None:
    """Map ingestion domain errors to HTTP responses (Module 12 contract)."""
    if isinstance(exc, InvalidURLError):
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RepoNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PrivateRepoError):
        raise HTTPException(
            status_code=403,
            detail=(
                f"{exc} This repository may be private. "
                "Provide a GitHub Personal Access Token (PAT) via GITHUB_TOKEN or embed credentials in the URL."
            ),
        )
    if isinstance(exc, NetworkTimeoutError):
        raise HTTPException(status_code=504, detail=str(exc))
    if isinstance(exc, RepoTooLargeError):
        raise HTTPException(
            status_code=413,
            detail=(
                f"{exc} Try a smaller repository or increase MAX_REPO_SIZE_MB in configuration."
            ),
        )
    raise HTTPException(status_code=500, detail=str(exc))

def _run_ingest_pipeline_remaining(job_id: str, clone_res: Any, files: list[Any], force_reindex: bool):
    """
    Remaining ingestion pipeline running in a FastAPI BackgroundTask.
    Spans Modules 5 → 7: parse → chunk → embed → BM25 → graph.
    """
    meta = metadata_store.get(job_id)
    repo_url = meta.repo_url if meta else ""
    log = logger.bind(job_id=job_id, repo_url=repo_url, job="ingest_pipeline")
    log.info("ingest_pipeline_started")
    try:
        # Module 5: Parse and Chunk
        contents = {}
        file_records = {}
        parsed_files = []

        for f in files:
            text, decode_err = safe_decode(Path(f.path))
            if decode_err or not text:
                continue
            contents[f.display_path] = text
            file_records[f.display_path] = (str(f.path), f.display_path, f.normalized_path)

            parsed = parse_file(str(f.path), text, f.language)
            if parsed:
                parsed.file_path = f.display_path
                parsed_files.append(parsed)

        chunks = chunk_all_files(parsed_files, contents, file_records)

        # Module 6: Embeddings & Vector Store + BM25
        store_chunks(job_id, chunks, force_reindex=force_reindex)
        build_bm25_index(job_id, chunks)

        # Module 7: Graph Builder
        build_graph(job_id, parsed_files)

        # Mark Synced
        metadata_store.mark_synced(
            job_id,
            commit_hash=clone_res.commit_hash,
            cloned_at=getattr(clone_res, 'cloned_at', '') or "",
        )
        log.info("ingest_pipeline_success")

    except Exception as e:
        log.exception("ingest_pipeline_failed")
        metadata_store.mark_failed(job_id, error_reason=str(e))
    finally:
        lock_manager.release(job_id)


def trigger_ingest(repo_url: str, ref: str | None, force_reindex: bool, bg_tasks: BackgroundTasks) -> IngestJobResponse:
    from app.ingestion.clone import _validate_url, InvalidURLError as _InvalidURLError
    try:
        _validate_url(repo_url)
    except _InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo_id = repo_id_for(repo_url, ref or "HEAD")

    # Check model mismatch synchronously (skip if Chroma unreachable)
    if not force_reindex:
        try:
            from app.retrieval.vector_store import get_collection
            from app.config import settings as app_settings
            col = get_collection(repo_id)
            if col and col.metadata:
                stored_model = col.metadata.get("embedding_model_id")
                if stored_model and stored_model != app_settings.EMBEDDING_MODEL:
                    raise HTTPException(
                        status_code=409,
                        detail="Embedding model mismatch. Pass force_reindex=true to rebuild."
                    )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("ingest_model_check_skipped", repo_id=repo_id, error=str(exc))

    # Acquire lock
    lock_res = lock_manager.try_acquire(repo_id, metadata_store)
    if not lock_res.acquired:
        return IngestJobResponse(job_id=repo_id, status="already_running")

    # Mark pending and return immediately — clone/parse/embed run in the worker.
    from app.platform.audit_log import record_event
    from app.platform.tenant_context import get_tenant
    from app.platform.usage_meter import check_quota, increment

    tenant = get_tenant()
    if not check_quota(tenant.org_id, "ingest"):
        lock_manager.release(repo_id)
        raise HTTPException(status_code=429, detail="Monthly ingest quota exceeded")

    metadata_store.mark_pending(repo_id, repo_url, ref or "HEAD")
    record_event(
        "ingest.started",
        org_id=tenant.org_id,
        resource_type="repository",
        resource_id=repo_id,
        details={"repo_url": repo_url},
    )
    increment(tenant.org_id, "ingest")

    from app.redis_client import ping_redis

    dispatched = False
    redis_up = ping_redis()
    if redis_up and _celery_workers_available():
        try:
            from app.tasks.ingestion_task import run_ingestion

            run_ingestion.delay(
                repo_url=repo_url,
                ref=ref,
                force_reindex=force_reindex,
                job_id=repo_id,
            )
            dispatched = True
        except Exception as e:
            logger.warning("celery_dispatch_failed_fallback_to_bg_tasks", error=str(e))
    elif redis_up:
        logger.warning(
            "celery_workers_unavailable_fallback_to_bg_tasks",
            repo_id=repo_id,
            hint=(
                "Redis is reachable but no Celery worker is consuming the ingestion queue. "
                "Start: celery -A app.tasks.celery_app worker -l info -Q ingestion --pool=solo"
            ),
        )

    if not dispatched:
        from app.ingestion.pipeline import run_ingestion_sync
        bg_tasks.add_task(
            run_ingestion_sync,
            repo_url,
            ref,
            force_reindex,
            repo_id,
        )

    return IngestJobResponse(job_id=repo_id, status="processing")


@router.post("/ingest", response_model=IngestJobResponse, status_code=202, dependencies=[Depends(verify_api_key)])
@limiter.limit("3/minute")
def ingest_repo(request: Request, req: IngestRequest, bg_tasks: BackgroundTasks, response: Response):
    job = trigger_ingest(str(req.repo_url), req.ref, req.force_reindex, bg_tasks)
    if job.status != "processing":
        response.status_code = 200
    return {"job_id": job.job_id, "status": job.status}



def _resolve_repo_meta(job_id: str) -> tuple[Any, str]:
    """Resolve job_id → asset_repo_id via app.repo_resolver."""
    from app.repo_resolver import resolve_asset_repo_id

    return resolve_asset_repo_id(job_id, store=metadata_store)


def _require_repo_ready(job_id: str, asset_repo_id: str | None = None) -> None:
    """Raise HTTP 409 when ingestion is incomplete — same gate as /status and Eval."""
    from app.ingestion.repo_readiness import is_repo_ready

    readiness = is_repo_ready(job_id, asset_repo_id=asset_repo_id)
    if not readiness.ready:
        detail = readiness.block_message or f"ingestion incomplete (status: {readiness.sync_status or 'missing'})"
        raise HTTPException(status_code=409, detail=detail)


def _enforce_repo_org(meta: Any) -> None:
    try:
        from app.platform.tenant_context import require_org_access
        require_org_access(getattr(meta, "org_id", None))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/status/public")
def get_public_status_alias():
    """Explicit path so ``/status/public`` is never captured by ``/status/{job_id}``."""
    from app.api.status_router import public_status

    return public_status()


@router.get("/status/{job_id}", dependencies=[Depends(verify_api_key)])
def get_ingest_status(job_id: str):
    _validate_repo_id(job_id)
    if job_id == "public":
        from app.api.status_router import public_status

        return public_status()

    meta, asset_repo_id = _resolve_repo_meta(job_id)

    if not meta:
        raise HTTPException(status_code=404, detail="Job/Repo not found.")

    _enforce_repo_org(meta)

    from app.ingestion.repo_readiness import evaluate_chat_readiness, readiness_snapshot

    readiness = evaluate_chat_readiness(
        job_id, asset_repo_id=asset_repo_id, store=metadata_store,
    )
    snap = readiness_snapshot(job_id, asset_repo_id=asset_repo_id, store=metadata_store)
    meta = readiness.meta or meta
    files_parsed = readiness.files_parsed
    chunks_created = readiness.chunks_created

    # We must construct the exact response from spec
    resp = {
        "job_id": job_id,
        "repo_id": job_id,
        "ref": meta.ref,
        "commit_hash": meta.commit_hash,
        "sync_status": meta.sync_status,
        "ready": snap["ready"],
        "error": getattr(meta, "error_reason", None),
        "files_parsed": files_parsed,
        "chunks_created": chunks_created,
        "asset_repo_id": snap["asset_repo_id"],
        "graph_truncated": False,
        "has_circular_dependencies": False,
        "status": "ready" if readiness.ready else _api_status_for_sync(meta.sync_status),
    }
    
    if Stage.is_failed(meta.sync_status):
        resp["error_reason"] = meta.error_reason
        resp["error"] = meta.error_reason
    elif Stage.is_synced(meta.sync_status):
        # Extract graph info
        try:
            import json
            from pathlib import Path
            from app.graph.queries import detect_cycles
            graph_repo_id = asset_repo_id
            graph_meta_file = Path(settings.GRAPH_STORE_PATH) / graph_repo_id / "graph.json"
            if graph_meta_file.exists():
                g_payload = json.loads(graph_meta_file.read_text())
                g_meta = g_payload.get("metadata", g_payload)
                resp["graph_truncated"] = g_meta.get("graph_truncated", False)
                stored_cycles = g_meta.get("has_circular_dependencies")
                if stored_cycles is None:
                    stored_cycles = detect_cycles(graph_repo_id)
                resp["has_circular_dependencies"] = stored_cycles
        except Exception as exc:
            logger.warning("status_graph_metadata_read_failed", error=str(exc))

    return resp


@router.get("/chat/stream/{session_id}", dependencies=[Depends(verify_api_key)])
async def chat_state_stream(request: Request, session_id: str):
    """SSE stream of live agent state transitions for one chat session."""
    from app.api.state_stream import async_stream

    return StreamingResponse(
        async_stream(session_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
def chat(request: Request, req: ChatRequest):
    _validate_repo_id(req.repo_id)
    from app.ingestion.repo_readiness import evaluate_chat_readiness

    meta, asset_repo_id = _resolve_repo_meta(req.repo_id)
    readiness = evaluate_chat_readiness(
        req.repo_id, asset_repo_id=asset_repo_id, store=metadata_store,
    )
    if readiness.block_reason == "unknown":
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    meta = readiness.meta or meta
    if meta:
        _enforce_repo_org(meta)
    from app.platform.usage_meter import check_quota, increment
    from app.platform.audit_log import record_event
    from app.platform.tenant_context import get_tenant

    tenant = get_tenant()
    if not check_quota(tenant.org_id, "chat"):
        raise HTTPException(status_code=429, detail="Monthly chat quota exceeded")
        
    chat_history = []
    session_file = None
    if req.session_id:
        session_file = Path(settings.DATA_PATH) / "sessions" / f"{req.session_id}.json"
        if session_file.exists():
            try:
                chat_history = json.loads(session_file.read_text())
            except Exception:
                chat_history = []

    try:
        if chat_history:
            result = run(
                asset_repo_id,
                req.question,
                req.session_id,
                job_id=req.repo_id,
                chat_history=chat_history,
            )
        else:
            result = run(asset_repo_id, req.question, req.session_id, job_id=req.repo_id)
            
        if req.session_id and "error" not in result:
            chat_history.append({"role": "user", "content": req.question})
            chat_history.append({"role": "assistant", "content": result.get("answer", "")})
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(json.dumps(chat_history[-10:])) # keep last 10 turns


        # If the loop handled a rate-limit gracefully it returns a dict with
        # rate_limited=True instead of raising an exception.  Surface that as
        # a proper 429 so the frontend can show a specific, actionable message.
        if result.get("timed_out") or (
            result.get("groq_failed") and "too slow" in str(result.get("answer", "")).lower()
        ):
            answer = str(result.get("answer") or "").strip()
            if answer:
                increment(tenant.org_id, "chat")
                record_event(
                    "chat.completed",
                    org_id=tenant.org_id,
                    resource_type="repository",
                    resource_id=req.repo_id,
                )
                return {
                    **result,
                    "gated": True,
                    "timed_out": True,
                }
            raise HTTPException(
                status_code=504,
                detail=(
                    "The request took too long to complete before any answer was ready. "
                    "Try a more specific question or retry shortly."
                ),
            )

        if result.get("rate_limited"):
            wait = int(result.get("retry_after_s") or 30)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"The AI provider is temporarily rate-limited. "
                    f"Please wait about {wait} seconds and try again."
                ),
                headers={"Retry-After": str(wait)},
            )

        increment(tenant.org_id, "chat")
        record_event(
            "chat.completed",
            org_id=tenant.org_id,
            resource_type="repository",
            resource_id=req.repo_id,
        )
        return result
    except HTTPException:
        raise  # re-raise 429 / 409 / etc. as-is
    except RateLimitError:
        # Safety net: RateLimitError escaped the loop (should not happen normally)
        raise HTTPException(
            status_code=429,
            detail=(
                "The AI provider is temporarily rate-limited. "
                "Please wait about 30 seconds and try again."
            ),
        )
    except Exception as e:
        # Check if it's the model mismatch error from the cache or vector store
        if "embedding_model_id mismatch" in str(e) or "dimension mismatch" in str(e).lower():
             raise HTTPException(status_code=409, detail="Embedding model mismatch on re-ingest. Please pass force_reindex=true to /ingest to rebuild.")
        
        # If it's a tenacity RetryError or an LLM timeout, return a clean 503/504
        # We check class name to avoid directly importing tenacity if we can
        err_str = str(type(e).__name__)
        if "RetryError" in err_str or "Timeout" in err_str:
            raise HTTPException(status_code=504, detail="LLM request timed out or failed after retries.")
            
        raise


@router.post("/diagram", response_model=DiagramResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit("5/minute")
def generate_diagram_endpoint(request: Request, req: DiagramRequest):
    _validate_repo_id(req.repo_id)
    meta, asset_repo_id = _resolve_repo_meta(req.repo_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    _enforce_repo_org(meta)
    _require_repo_ready(req.repo_id, asset_repo_id)
        
    try:
        depth = 2
        sub = get_subgraph(asset_repo_id, req.entry_point, direction=req.direction, max_depth=depth)
        sub_with_entry = {**sub, "entry_point": req.entry_point}
        mermaid_markdown = generate_mermaid(sub_with_entry, direction=req.direction, repo_id=asset_repo_id)
        return {"mermaid_markdown": mermaid_markdown}
    except ValueError as e:
        if "not found in graph" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/onboarding-path", response_model=OnboardingPathResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit("5/minute")
def generate_onboarding_path(request: Request, req: OnboardingPathRequest):
    _validate_repo_id(req.repo_id)
    meta, asset_repo_id = _resolve_repo_meta(req.repo_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    _enforce_repo_org(meta)
    _require_repo_ready(req.repo_id, asset_repo_id)

    try:
        from app.agent.onboarding_path import build_path

        path = build_path(asset_repo_id, req.role, req.experience_level)
        return {"onboarding_path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{repo_id}", dependencies=[Depends(verify_api_key)])
def get_symbols_endpoint(repo_id: str):
    _validate_repo_id(repo_id)
    meta, asset_repo_id = _resolve_repo_meta(repo_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    _enforce_repo_org(meta)
    _require_repo_ready(repo_id, asset_repo_id)

    from app.graph.queries import _get_graph
    graph = _get_graph(asset_repo_id)
    if not graph:
        return []

    symbols = []
    for n, attr in graph.nodes(data=True):
        symbols.append({
            "id": n,
            "name": attr.get("name") or n,
            "path": attr.get("path") or "",
            "type": attr.get("type") or "",
            "start_line": attr.get("start_line"),
            "end_line": attr.get("end_line"),
        })
    return symbols


@router.get("/file-snippet/{repo_id}", dependencies=[Depends(verify_api_key)])
def get_file_snippet_endpoint(
    repo_id: str,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
):
    _validate_repo_id(repo_id)
    meta, asset_repo_id = _resolve_repo_meta(repo_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    _enforce_repo_org(meta)
    _require_repo_ready(repo_id, asset_repo_id)

    from app.config import settings
    repo_dir = Path(settings.REPOS_PATH) / asset_repo_id

    # Normalize file_path: strip any leading "/" or "./" so that
    # Path(repo_dir) / "/src/foo.py" doesn't silently become an absolute path
    # on Linux (which bypasses the traversal guard and causes 404).
    normalized_path = file_path.lstrip("/").lstrip("\\")
    full_path = repo_dir / normalized_path

    # Security check: prevent directory traversal
    try:
        full_path.resolve().relative_to(repo_dir.resolve())
    except ValueError:
        logger.warning(
            "file_snippet.traversal_blocked",
            extra={
                "repo_id": repo_id,
                "file_path": file_path,
                "normalized_path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
            },
        )
        raise HTTPException(status_code=403, detail="Forbidden path traversal")

    if not full_path.exists() or not full_path.is_file():
        logger.warning(
            "file_snippet.file_not_found",
            extra={
                "repo_id": repo_id,
                "file_path": file_path,
                "normalized_path": normalized_path,
                "resolved_path": str(full_path),
                "start_line": start_line,
                "end_line": end_line,
                "error_type": "file_not_found",
            },
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"Source file '{normalized_path}' not found in the indexed repository. Try re-ingesting this repo to refresh snippets.",
                "error_type": "file_not_found",
                "file_path": normalized_path,
            },
        )

    try:
        from app.ingestion.file_filter import safe_decode
        text, _ = safe_decode(full_path)
        if not text:
            logger.info(
                "file_snippet.empty_file",
                extra={
                    "repo_id": repo_id,
                    "file_path": normalized_path,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
            return {
                "code": "",
                "start_line": 1,
                "end_line": 0,
                "total_lines": 0,
                "error_type": "empty_file",
            }
        lines = text.splitlines()

        if start_line is not None and end_line is not None:
            # Validate line numbers are in bounds before slicing
            if start_line > len(lines):
                logger.warning(
                    "file_snippet.line_out_of_bounds",
                    extra={
                        "repo_id": repo_id,
                        "file_path": normalized_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "total_lines": len(lines),
                        "error_type": "line_out_of_bounds",
                    },
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": f"Line {start_line} is out of bounds — the file only has {len(lines)} lines. The index may be stale. Try re-ingesting this repo.",
                        "error_type": "line_out_of_bounds",
                        "file_path": normalized_path,
                        "start_line": start_line,
                        "total_lines": len(lines),
                    },
                )

            # 1-indexed slice, apply context padding of 5 lines
            s_idx = max(0, start_line - 1 - 5)
            e_idx = min(len(lines), end_line + 5)
            snippet = "\n".join(lines[s_idx:e_idx])
            logger.info(
                "file_snippet.success",
                extra={
                    "repo_id": repo_id,
                    "file_path": normalized_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "snippet_lines": e_idx - s_idx,
                },
            )
            return {
                "code": snippet,
                "start_line": s_idx + 1,
                "end_line": e_idx,
                "total_lines": len(lines),
            }

        logger.info(
            "file_snippet.full_file",
            extra={
                "repo_id": repo_id,
                "file_path": normalized_path,
                "total_lines": len(lines),
            },
        )
        return {
            "code": text,
            "start_line": 1,
            "end_line": len(lines),
            "total_lines": len(lines),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "file_snippet.unexpected_error",
            extra={
                "repo_id": repo_id,
                "file_path": normalized_path,
                "start_line": start_line,
                "end_line": end_line,
                "error": str(exc),
                "error_type": "decode_error",
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Failed to read source file '{normalized_path}': {exc}",
                "error_type": "decode_error",
                "file_path": normalized_path,
            },
        )



@router.get("/diagram/{repo_id}", dependencies=[Depends(verify_api_key)])
def get_function_diagram_query(
    repo_id: str,
    function_name: str,
    depth: int = 2,
    direction: str | None = None,
):
    _validate_repo_id(repo_id)
    """Backward-compatible route used by tests and older clients (function_name as query param)."""
    return get_function_diagram(repo_id, function_name, depth, direction=direction)


@router.get("/diagram/{repo_id}/{function_name}", dependencies=[Depends(verify_api_key)])
def get_function_diagram(
    repo_id: str,
    function_name: str,
    depth: int = 2,
    direction: str | None = None,
):
    _validate_repo_id(repo_id)
    from app.debug_trace import debug_log

    meta, asset_repo_id = _resolve_repo_meta(repo_id)
    debug_log(
        "router.py:get_function_diagram",
        "diagram_lookup",
        {
            "job_id": repo_id,
            "asset_repo_id": asset_repo_id,
            "function_name": function_name,
            "depth": depth,
            "sync_status": getattr(meta, "sync_status", None),
        },
        hypothesis_id="B",
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown repo_id")
    _enforce_repo_org(meta)
    _require_repo_ready(repo_id, asset_repo_id)

    from app.config import settings

    traversal = (direction or settings.DIAGRAM_DEFAULT_DIRECTION).strip().lower()
    if traversal not in ("upstream", "downstream", "both"):
        traversal = settings.DIAGRAM_DEFAULT_DIRECTION
        
    try:
        sub = get_subgraph(
            asset_repo_id,
            function_name,
            direction=traversal,
            max_depth=depth,
        )
        sub_with_entry = {**sub, "entry_point": function_name}
        debug_log(
            "router.py:get_function_diagram",
            "subgraph_result",
            {
                "asset_repo_id": asset_repo_id,
                "node_count": len(sub.get("nodes", [])),
                "edge_count": len(sub.get("edges", [])),
                "not_found": sub.get("not_found", False),
                "truncated_count": sub.get("truncated_count", 0),
                "direction": traversal,
            },
            hypothesis_id="B,C",
        )
        return graph_to_mermaid(
            sub_with_entry,
            sub.get("requested_depth", depth),
            3 if sub.get("clamped") else sub.get("requested_depth", depth),
            max_nodes=settings.GRAPH_SUBGRAPH_MAX_NODES,
            repo_id=asset_repo_id,
            direction=traversal,
        )
    except ValueError as e: # Function not found
        if "not found in graph" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise


# ---------------------------------------------------------------------------
# Eval job store (Redis + disk; see app/jobs/eval_job_store.py)
# ---------------------------------------------------------------------------
from app.jobs.eval_job_store import get_eval_job, set_eval_job


def _set_eval_job(job_id: str, **updates: Any) -> None:
    set_eval_job(job_id, **updates)


def _run_job_with_timeout(
    job_id: str,
    label: str,
    worker,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run a blocking eval worker with a wall-clock cap so jobs always terminate."""
    from app.config import settings
    import concurrent.futures

    limit = max(120, int(settings.EVAL_JOB_MAX_SECONDS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker, *args, **kwargs)
        try:
            return future.result(timeout=limit)
        except concurrent.futures.TimeoutError as exc:
            msg = f"{label} timed out after {limit}s"
            _set_eval_job(job_id, status="error", error=msg)
            raise TimeoutError(msg) from exc


def _run_eval_background(eval_job_id: str) -> None:
    """Execute the RAGAS eval suite in a background thread."""
    from app.debug_trace import debug_log

    job = get_eval_job(eval_job_id) or {}
    target_repo = job.get("target_repo_id")

    _set_eval_job(eval_job_id, status="running")

    try:
        debug_log(
            "router.py:_run_eval_background",
            "eval_import_start",
            {"target_repo_id": target_repo},
            hypothesis_id="A",
        )
        from eval.run_eval import run_eval as execute_eval
        res = _run_job_with_timeout(
            eval_job_id,
            "RAGAS evaluation",
            execute_eval,
            target_repo_id=target_repo,
        )
        res["supplementary"] = {
            "mean_confidence_score": res.get("mean_confidence_score"),
            "average_iterations": res.get("average_iterations"),
            "invalid_reference_rate": res.get("invalid_reference_rate"),
            "retrieval_precision_at_3": res.get("retrieval_precision_at_3"),
        }
        _set_eval_job(eval_job_id, status="done", result=res)
    except TimeoutError:
        return
    except Exception as exc:
        from app.debug_trace import debug_log
        debug_log(
            "router.py:_run_eval_background",
            "eval_failed",
            {"error": str(exc), "error_type": type(exc).__name__},
            hypothesis_id="A",
        )
        _set_eval_job(eval_job_id, status="error", error=str(exc))


@router.post("/eval/run", dependencies=[Depends(verify_api_key)])
@router.get("/eval/run", dependencies=[Depends(verify_api_key)])
def run_eval_endpoint(repo_id: str | None = None):
    """
    Start an async RAGAS evaluation run.
    Returns immediately with a job_id.
    Poll /eval/status/{job_id} to check progress.
    """
    if repo_id:
        _validate_repo_id(repo_id)
    from app.platform.tenant_context import get_tenant
    from app.platform.usage_meter import check_quota, increment
    from eval.health_check import run_full_eval_precheck

    tenant = get_tenant()
    if not check_quota(tenant.org_id, "eval"):
        raise HTTPException(status_code=429, detail="Monthly eval quota exceeded")

    target_repo = (repo_id or "").strip()
    if not target_repo:
        raise HTTPException(
            status_code=400,
            detail=(
                "repo_id is required — pass the active ingested repository from the UI "
                "(session job_id). Eval cannot run without a target repo."
            ),
        )

    precheck = run_full_eval_precheck(target_repo, include_agent_probe=False)
    if not precheck.ok:
        raise HTTPException(
            status_code=412,
            detail={
                "message": "Evaluation pre-check failed. Fix index/ingest before running eval.",
                "errors": precheck.errors,
                "details": precheck.details,
            },
        )

    eval_job_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4().hex
    increment(tenant.org_id, "eval")
    _set_eval_job(
        eval_job_id,
        status="queued",
        started_at=datetime.now(timezone.utc).isoformat(),
        target_repo_id=target_repo,
        correlation_id=correlation_id,
        job_type="ragas",
        result=None,
        error=None,
    )
    thread = threading.Thread(target=_run_eval_background, args=(eval_job_id,), daemon=True)
    thread.start()
    return {"job_id": eval_job_id, "status": "queued", "correlation_id": correlation_id}


@router.get("/eval/health/{repo_id}", dependencies=[Depends(verify_api_key)])
def eval_health(repo_id: str, probe_agent: bool = False):
    """
    Pre-evaluation health check for a repo (job_id or asset id).
    Set probe_agent=true to also run a live agent answer probe (uses Groq tokens).
    """
    _validate_repo_id(repo_id)
    from eval.health_check import run_full_eval_precheck

    result = run_full_eval_precheck(repo_id, include_agent_probe=probe_agent)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "details": result.details,
    }


@router.get("/eval/status/{job_id}", dependencies=[Depends(verify_api_key)])
def eval_status(job_id: str):
    _validate_eval_job_id(job_id)
    """
    Poll the status of an async eval job.
    Status values: queued | running | done | error
    When done, the full result is included in the response.
    """
    job = get_eval_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Eval job {job_id!r} not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "started_at": job.get("started_at"),
        "correlation_id": job.get("correlation_id"),
        "job_type": job.get("job_type"),
        "result": job.get("result"),
        "error": job.get("error"),
    }


@router.get("/eval/status", dependencies=[Depends(verify_api_key)])
def eval_status_summary():
    """
    Return the last 5 evaluation runs from eval history.
    """
    from eval.eval_store import load_runs

    return load_runs(newest_first=True)[:5]

@router.get("/eval/history", dependencies=[Depends(verify_api_key)])
def eval_history():
    """
    Return all evaluation runs, newest first.
    """
    from eval.eval_store import load_runs

    return load_runs(newest_first=True)


class CompareRequest(BaseModel):
    baseline_version: str
    candidate_version: str
    tolerance: float = 0.05

@router.post("/eval/compare", dependencies=[Depends(verify_api_key)])
def eval_compare(req: CompareRequest):
    try:
        from eval.compare_runs import compare_eval_runs as execute_compare
        return execute_compare(req.baseline_version, req.candidate_version, req.tolerance)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/eval/compare", dependencies=[Depends(verify_api_key)])
def eval_compare_get(baseline: str, candidate: str, tolerance: float = 0.05):
    try:
        from eval.compare_runs import compare_eval_runs as execute_compare
        return execute_compare(baseline, candidate, tolerance)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/eval/golden-status", dependencies=[Depends(verify_api_key)])
def eval_golden_status():
    import json as _json
    status_path = Path("tests/golden_set_status.json")
    if not status_path.exists():
        return {"status": "not_yet_run"}
    try:
        with status_path.open("r", encoding="utf-8") as fh:
            data = _json.loads(fh.read())
        # Surface staleness so the UI never presents an old result as current.
        ts = data.get("timestamp")
        if ts:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
                data["age_seconds"] = int(age)
                data["stale"] = age > 24 * 3600
            except Exception:
                pass
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _run_golden_background(job_id: str) -> None:
    _set_eval_job(job_id, status="running")
    try:
        from eval.golden_runner import run_golden_set
        result = _run_job_with_timeout(job_id, "Golden CI", run_golden_set)
        _set_eval_job(job_id, status="done", result=result)
    except TimeoutError:
        return
    except Exception as exc:
        _set_eval_job(job_id, status="error", error=str(exc))


@router.post("/eval/golden/run", dependencies=[Depends(verify_api_key)])
@router.get("/eval/golden/run", dependencies=[Depends(verify_api_key)])
def run_golden_endpoint():
    """Trigger a fresh Golden Set CI run; poll /eval/status/{job_id}."""
    job_id = uuid.uuid4().hex
    correlation_id = uuid.uuid4().hex
    _set_eval_job(
        job_id,
        status="queued",
        started_at=datetime.now(timezone.utc).isoformat(),
        correlation_id=correlation_id,
        job_type="golden",
        result=None,
        error=None,
    )
    thread = threading.Thread(target=_run_golden_background, args=(job_id,), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued", "correlation_id": correlation_id}

