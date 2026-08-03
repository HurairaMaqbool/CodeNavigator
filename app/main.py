# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/main.py
-----------
FastAPI application entry-point — Module 2 (Layer 1: Configuration & Bootstrap).

Import order rule (enforced):
  1. app/config.py settings singleton  ← validated before ANY other import
  2. Logging configuration              ← must fire before any log call
  3. Middleware, exception handlers, routers

Public API for tests and external wiring:
  create_app()      → FastAPI   factory so tests build isolated instances
  on_startup()      → None      warms embedding + reranker models (side effects only)
  global_exception_handler(request, exc) → JSONResponse  (never leaks stack traces)

The app singleton at module-level is the uvicorn target: app.main:app
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# ① Chroma telemetry silencer — must run before chromadb is imported anywhere.
#    This is a process-level env flag, not business config, so it precedes
#    the settings import deliberately.
# ---------------------------------------------------------------------------
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
import app.chroma_client  # noqa: F401 — disables PostHog before any chromadb import

# ---------------------------------------------------------------------------
# ② CONFIG FIRST — the single mandatory prerequisite before everything else.
#    If settings validation fails (bad env), the import raises immediately and
#    the process exits before any router, model, or middleware is wired up.
# ---------------------------------------------------------------------------
from app.config import settings  # noqa: E402  (must come before all downstream imports)

# ---------------------------------------------------------------------------
# ③ LOGGING — configure structlog before any log call fires, including those
#    inside lifespan/startup handlers or middleware constructors.
# ---------------------------------------------------------------------------
from app.observability.logging_config import configure_logging, logger  # noqa: E402

configure_logging()

# ---------------------------------------------------------------------------
# ④ Standard library + third-party imports (safe now that config is valid)
# ---------------------------------------------------------------------------
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.rate_limiter import limiter


# ===========================================================================
# MODEL WARM-UP
# ===========================================================================

def on_startup() -> None:
    """
    Preload the embedding model and Cross-Encoder reranker into memory so
    the very first real request is not slowed by a cold model initialisation.

    Spec contract
    -------------
    * Runs exactly once at process start, inside the FastAPI lifespan event.
    * Runs synchronously before the app accepts traffic.
    * Any warm-up failure aborts startup (fail fast, fail closed).
    * COST NOTE: both models are local HuggingFace models — zero Groq calls,
      zero external API cost.
    """
    from app.retrieval.embeddings import get_model as _get_embedder

    _get_embedder()
    logger.info("embedding_model_warmed")

    if settings.ENABLE_RERANKER:
        from app.retrieval.reranker import _get_model as _get_reranker

        _get_reranker()
        logger.info("reranker_model_warmed")

    logger.info("model_warmup_complete")


# ===========================================================================
# LIFESPAN (FastAPI 0.93+ async context manager — replaces on_event hooks)
# ===========================================================================

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """
    Async lifespan context manager.

    Startup sequence:
    1. Optional: initialise PostgreSQL schema if DATABASE_URL is configured.
    2. Synchronously warm embedding + reranker models (abort startup on failure).

    Shutdown: no explicit teardown needed for stateless in-process state.

    Error handling: model warm-up failures abort startup. PostgreSQL bootstrap
    failures are logged but non-fatal (platform tier is optional).
    """
    import os
    import threading

    # Optional PostgreSQL schema bootstrap (platform tier only)
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

    # Model warm-up — synchronous in production; skipped under pytest (lazy load in tests).
    logger.info("model_warmup_started")
    if os.environ.get("PYTEST_RUNNING"):
        logger.info("model_warmup_skipped", reason="pytest")
    else:
        on_startup()

    def _consistency_loop() -> None:
        import time

        while True:
            try:
                from app.ingestion.repo_readiness import audit_all_repos_consistency

                audit_all_repos_consistency()
            except Exception as exc:
                logger.warning("repo_consistency_audit_failed", error=str(exc))
            time.sleep(300)

    threading.Thread(target=_consistency_loop, daemon=True, name="repo-consistency-audit").start()

    yield
    # No shutdown teardown required for current scope


# ===========================================================================
# APPLICATION FACTORY
# ===========================================================================

def create_app(override_settings=None) -> FastAPI:
    """
    FastAPI application factory.

    Parameters
    ----------
    override_settings : Settings | None
        When provided, replaces the process-wide ``settings`` singleton for
        the duration of this app instance. Intended exclusively for test
        isolation — never pass this in production code.

    Returns
    -------
    FastAPI
        A fully wired ASGI application with middleware, exception handlers,
        and all routers registered. Ready to pass to uvicorn or an ASGI test
        client.

    Design note
    -----------
    Using a factory pattern (rather than a bare module-level ``app`` object)
    means pytest can spin up a fresh, isolated FastAPI instance for each test
    suite with a different ``override_settings``, preventing state leakage
    between test runs.
    """
    _cfg = override_settings or settings

    # Conditionally expose OpenAPI docs (hidden in production per spec)
    _show_docs = not (
        _cfg.ENVIRONMENT.lower() == "production" and _cfg.DISABLE_OPENAPI_IN_PRODUCTION
    )

    _app = FastAPI(
        title="CodeNavigator",
        description="AI-powered codebase onboarding assistant.",
        version="1.0.0",
        docs_url="/docs" if _show_docs else None,
        redoc_url="/redoc" if _show_docs else None,
        openapi_url="/openapi.json" if _show_docs else None,
        lifespan=_lifespan,
    )

    # ── Observability ────────────────────────────────────────────────────────
    from app.observability.tracing import setup_tracing
    setup_tracing()

    if _cfg.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=_cfg.SENTRY_DSN,
                traces_sample_rate=1.0,
                profiles_sample_rate=1.0,
            )
            logger.info("sentry_enabled")
        except Exception as exc:
            logger.warning("sentry_init_failed", error=str(exc))

    try:
        if not os.environ.get("PYTEST_RUNNING") and _cfg.OTEL_ENDPOINT:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(_app)
    except Exception:
        pass  # OTel is optional — absence must never crash startup

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(_app).expose(_app, endpoint="/metrics")
    except Exception:
        pass  # Prometheus is optional

    # ── Rate limiter ─────────────────────────────────────────────────────────
    limiter.enabled = (_cfg.ENVIRONMENT.lower() not in ("development", "testing"))
    _app.state.limiter = limiter
    _app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS middleware ───────────────────────────────────────────────────────
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=_cfg.ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Authorization", "X-Hub-Signature-256"],
    )

    # ── Request-ID middleware (added after CORS, applied inner-first) ─────────
    _app.add_middleware(RequestIDMiddleware)

    # ── Metrics auth middleware ───────────────────────────────────────────────
    _app.add_middleware(MetricsAuthMiddleware)

    # ── Exception handlers ───────────────────────────────────────────────────
    _app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    _app.add_exception_handler(Exception, global_exception_handler)

    # ── Routers (Module #3: app/api/router.py — forward import) ──────────────
    # Each router is imported lazily so a missing module during incremental
    # builds raises an ImportError with a clear message rather than a
    # cryptic AttributeError at request time.
    _register_routers(_app)

    return _app


def _register_routers(_app: FastAPI) -> None:
    """
    Mount all API and webhook routers onto the app instance.

    Routers are imported here (not at module top-level) so each can be
    independently stubbed or replaced during testing.
    """
    # Public status MUST mount before /status/{job_id} or "public" is captured as a job_id.
    from app.api.status_router import router as status_router
    _app.include_router(status_router)

    # Core REST API (Module #3 — app/api/router.py)
    from app.api.router import router as api_router
    _app.include_router(api_router)

    # Platform / billing / auth (higher-tier features)
    from app.api.platform_router import router as platform_router
    _app.include_router(platform_router)

    from app.api.billing_router import router as billing_router
    _app.include_router(billing_router)

    from app.api.sso_router import router as sso_router
    _app.include_router(sso_router)

    from app.api.saml_router import router as saml_router
    _app.include_router(saml_router)

    # Webhook handlers
    from app.webhook.github_webhook import router as webhook_router
    _app.include_router(webhook_router)

    from app.webhook.github_app_webhook import router as github_app_webhook_router
    _app.include_router(github_app_webhook_router)

    from app.webhook.stripe_webhook import router as stripe_webhook_router
    _app.include_router(stripe_webhook_router)

    # Built-in health endpoint
    @_app.get("/health", tags=["observability"])
    async def health() -> JSONResponse:
        """
        Liveness check.

        Verification targets for Module 2:
        - Response carries X-Request-ID header (set by RequestIDMiddleware).
        - Each call produces a distinct request_id in stdout JSON logs.
        - No stack traces leak in the response body.
        """
        logger.info("health_check")
        return JSONResponse({"status": "ok", "version": _app.version})


# ===========================================================================
# MIDDLEWARE
# ===========================================================================

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Per-request UUID4 tracing middleware.

    For every HTTP request:
    1. Generate a fresh UUID4 as ``request_id``.
    2. Bind ``request_id`` + ``path`` into structlog contextvars so every
       log line emitted anywhere during that request carries both fields
       automatically — no extra instrumentation at call sites.
    3. Echo ``X-Request-ID`` on the response for client-side bug reporting.
    4. Clear contextvars after the response to prevent context leaking into
       the next request on the same asyncio task / thread.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
        )

        logger.info("request_started", method=request.method)

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            logger.exception("unhandled_exception_in_middleware", error=str(exc))
            is_prod = settings.ENVIRONMENT.lower() == "production"
            detail = (
                "Internal server error. Please quote the request_id when reporting."
                if is_prod
                else str(exc)
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": "An unexpected server error occurred. Please check the logs.",
                    "error_code": "INTERNAL_ERROR",
                    "message": detail,
                    "detail": detail,
                },
            )

        logger.info(
            "request_finished",
            method=request.method,
            status_code=response.status_code,
        )

        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response


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
                return JSONResponse(
                    status_code=403,
                    content={"error": "Forbidden", "error_code": "FORBIDDEN", "message": "Valid API key required"},
                )
        return await call_next(request)


# ===========================================================================
# EXCEPTION HANDLERS
# ===========================================================================

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP 4xx/5xx exceptions raised by FastAPI/Starlette route handlers.

    Returns a single {error, error_code, message} shape — consistent with the
    global_exception_handler so clients never have to parse two different
    error envelopes.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "message": str(exc.detail),
            "detail": exc.detail,
        },
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions that escape route handlers.

    Spec requirements
    -----------------
    * Never leak a stack trace or raw internal exception to the client response in production.
    * Log the full trace server-side, bound to the current request_id.
    * Return a single {error, error_code, message} JSON envelope so the
      API surface is consistent regardless of exception type.
    """
    # Full trace goes to the log, never to the HTTP response
    logger.exception("unhandled_exception", error=str(exc))

    ctx = structlog.contextvars.get_contextvars()
    req_id = ctx.get("request_id", "unknown")

    is_prod = settings.ENVIRONMENT.lower() == "production"
    detail = (
        "Internal server error. Please quote the request_id when reporting."
        if is_prod
        else str(exc)
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected server error occurred. Please check the logs.",
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please quote the request_id when reporting.",
            "detail": detail,
            "request_id": req_id,
        },
    )


# ===========================================================================
# MODULE-LEVEL APP SINGLETON
# ===========================================================================

# This is the uvicorn target: uvicorn app.main:app
# It is also importable by tests that want the pre-built singleton rather
# than constructing a fresh app via create_app().
app: FastAPI = create_app()
