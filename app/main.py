# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/main.py
-----------
FastAPI application entry-point.

Module 2 additions:
  - configure_logging() called once at startup (before middleware registration).
  - RequestIDMiddleware: generates UUID4 per request, binds request_id + path
    into structlog contextvars, echoes X-Request-ID response header.
  - /health endpoint for liveness checks and middleware verification.

Later modules will add their own routers via app.include_router(…).
"""

from __future__ import annotations

import os

# Disable Chroma telemetry noise in local/dev runs.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
import app.chroma_client  # noqa: F401 — disables PostHog before any chromadb import

from contextlib import asynccontextmanager

import uuid
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.rate_limiter import limiter

from app.observability.logging_config import configure_logging, logger
from app.config import settings

# ---------------------------------------------------------------------------
# Logging must be configured before any log call, including any that fire
# during module import or lifespan startup. Do it here, at the top, before
# the app object is even created.
# ---------------------------------------------------------------------------
configure_logging()

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

def _warm_models() -> None:
    try:
        from app.retrieval.embeddings import _get_model as _get_embedder
        _get_embedder()
    except Exception as exc:
        logger.warning("embedding_warmup_failed", error=str(exc))
    try:
        from app.retrieval.reranker import _get_model as _get_reranker
        if settings.ENABLE_RERANKER:
            _get_reranker()
    except Exception as exc:
        logger.warning("reranker_warmup_failed", error=str(exc))
    logger.info("model_warmup_complete")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    import threading

    if settings.DATABASE_URL:
        try:
            from app.platform.db.postgres import apply_schema, check_connection
            apply_schema()
            if check_connection():
                logger.info("postgres_ready")
            else:
                logger.warning("postgres_schema_applied_but_ping_failed")
        except Exception as exc:
            logger.warning("postgres_init_failed", error=str(exc))

    logger.info("model_warmup_started")
    threading.Thread(target=_warm_models, daemon=True).start()
    yield


_configure_docs = not (
    settings.ENVIRONMENT.lower() == "production" and settings.DISABLE_OPENAPI_IN_PRODUCTION
)

app = FastAPI(
    title="CodeNavigator",
    description="AI-powered codebase onboarding assistant.",
    version="1.0.0",
    docs_url="/docs" if _configure_docs else None,
    redoc_url="/redoc" if _configure_docs else None,
    openapi_url="/openapi.json" if _configure_docs else None,
    lifespan=_lifespan,
)

# ---------------------------------------------------------------------------
# Observability Init
# ---------------------------------------------------------------------------
from app.observability.tracing import setup_tracing
setup_tracing()

if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    logger.info("sentry_enabled")

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
except Exception:
    pass

try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
except Exception:
    pass


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    """Require API key for /metrics in production when PROTECT_METRICS=true."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if (
            request.url.path == "/metrics"
            and settings.ENVIRONMENT.lower() == "production"
            and settings.PROTECT_METRICS
        ):
            from app.platform.api_keys import resolve_api_key
            key = request.headers.get("X-API-Key", "")
            if resolve_api_key(key) is None:
                return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return await call_next(request)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type", "X-Hub-Signature-256"],
)

# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    For every incoming HTTP request:

    1. Generate a fresh UUID4 as ``request_id``.
    2. Bind ``request_id`` and ``path`` into structlog's contextvars so every
       log line emitted *anywhere* during that request — ingestion, agent loop,
       tool calls — automatically carries both fields with zero extra code at
       the call site.
    3. Clear the contextvars after the response is sent so leaked context
       never bleeds into a subsequent request on the same thread/task.
    4. Echo ``X-Request-ID`` on the response so callers can hand back the
       exact ID when reporting a bug.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())

        # Bind into structlog contextvars for this request's lifetime.
        # structlog.contextvars.bind_contextvars is async-safe (uses
        # contextvars.ContextVar under the hood, so each asyncio task gets
        # its own copy — no cross-request leakage).
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
        )

        logger.info(
            "request_started",
            method=request.method,
        )

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            from fastapi.exceptions import HTTPException as FastAPIHTTPException
            from starlette.exceptions import HTTPException as StarletteHTTPException
            if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"error": exc.detail, "code": "HTTP_ERROR", "detail": exc.detail}
                )
            else:
                logger.exception("unhandled_exception", error=str(exc))
                detail = str(exc) if settings.ENVIRONMENT.lower() != "production" else "Internal server error"
                response = JSONResponse(
                    status_code=500,
                    content={
                        "error": "An unexpected server error occurred. Please check the logs.",
                        "code": "INTERNAL_ERROR",
                        "detail": detail,
                    },
                )

        logger.info(
            "request_finished",
            method=request.method,
            status_code=response.status_code,
        )

        # Echo the ID so clients can quote it in bug reports.
        response.headers["X-Request-ID"] = request_id

        # Clean up — prevents context leaking to the next request if the
        # event loop reuses the same task for a different connection.
        structlog.contextvars.clear_contextvars()

        return response




app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsAuthMiddleware)


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------

from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "detail": exc.detail
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import structlog
    log = structlog.get_logger()
    
    log.exception("unhandled_exception", error=str(exc))
    ctx = structlog.contextvars.get_contextvars()
    req_id = ctx.get("request_id", "unknown")
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": req_id
        }
    )

# ---------------------------------------------------------------------------
# Routes — specific paths before parameterized /status/{job_id}
# ---------------------------------------------------------------------------

from app.api.status_router import router as status_router
app.include_router(status_router)

from app.api.router import router as api_router
app.include_router(api_router)

from app.api.platform_router import router as platform_router
app.include_router(platform_router)

from app.api.billing_router import router as billing_router
app.include_router(billing_router)

from app.api.sso_router import router as sso_router
app.include_router(sso_router)

from app.webhook.stripe_webhook import router as stripe_webhook_router
app.include_router(stripe_webhook_router)

from app.webhook.github_app_webhook import router as github_app_webhook_router
app.include_router(github_app_webhook_router)

from app.webhook.github_webhook import router as webhook_router
app.include_router(webhook_router)

from app.api.saml_router import router as saml_router
app.include_router(saml_router)


@app.get("/health", tags=["observability"])
async def health() -> JSONResponse:
    """
    Liveness check.

    Also serves as the manual verification target for Module 2:
    - The stdout JSON log should include ``request_id`` and ``path``.
    - The response should carry the ``X-Request-ID`` header.
    - Each call should produce a *distinct* ``request_id``.
    """
    logger.info("health_check")
    return JSONResponse({"status": "ok", "version": app.version})
