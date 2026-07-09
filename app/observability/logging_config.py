# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/observability/logging_config.py
------------------------------------
Structured JSON logging for the codenavigator.

LOGGING DISCIPLINE CONTRACT — read before adding log calls anywhere in this repo
----------------------------------------------------------------------------------
1. NEVER log secrets or full file/chunk text.
   • No API keys (GROQ_API_KEY, GITHUB_WEBHOOK_SECRET, …)
   • No full file contents or retrieved chunk text — even at DEBUG level.
   • Truncate or omit large blobs; log IDs, sizes, or hashes instead.

2. ALWAYS log structured fields, never pre-formatted strings.
   CORRECT:   log.info("tool_call", tool=name, latency_ms=120, cache_hit=False)
   INCORRECT: log.info(f"tool_call: {name} took 120ms, cache_hit=False")
   Structured fields are filterable/queryable in log aggregators and in
   plain `grep`. Pre-formatted strings are just noise.

3. ALWAYS bind sub-context at the entry point of a component, not at every call.
   Pattern (e.g. in ingestion):
       log = logger.bind(repo_id=repo_id)
       ...
       log.info("clone_started", size_mb=size)   # repo_id appears automatically
   This module's contextvars approach means nested binds compose with the
   request-scoped request_id already in context — no threading required.

4. The full debugging story for this project is:
       docker compose logs -f api
   No log aggregator, no log files, no external log shipping.
   stdout JSON  →  docker / compose  →  developer. That's it.

Usage
-----
    from app.observability.logging_config import configure_logging, logger

    configure_logging()          # call once at app startup (idempotent)
    logger.info("event", key=v)  # use anywhere; request_id appears automatically
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.config import settings

# ---------------------------------------------------------------------------
# Idempotency guard — prevent double-configuration if called from both
# app/main.py startup and a pytest fixture.
# ---------------------------------------------------------------------------
_configured: bool = False


def configure_logging() -> None:
    """
    Configure structlog for JSON-to-stdout output.

    Safe to call multiple times — subsequent calls are no-ops, so test
    fixtures can call this without duplicating processors or handler chains.
    """
    global _configured
    if _configured:
        return

    log_level: int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # ── stdlib root logger ───────────────────────────────────────────────────
    # Point stdlib through structlog so third-party libraries (uvicorn, fastapi)
    # emit in the same JSON format rather than in their own text format.
    logging.basicConfig(
        format="%(message)s",          # structlog handles formatting
        stream=sys.stdout,
        level=log_level,
        force=True,                    # override any earlier basicConfig calls
    )
    # Quiet uvicorn's own access logger — we handle access logging via middleware
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False

    # ── structlog pipeline ───────────────────────────────────────────────────
    shared_processors: list[Any] = [
        # 1. Merge any context bound via structlog.contextvars.bind_contextvars()
        #    (e.g. request_id bound by middleware, repo_id bound by ingestion).
        structlog.contextvars.merge_contextvars,
        # 2. Inject the stdlib log level name ("info", "warning", …).
        structlog.stdlib.add_log_level,
        # 3. ISO-8601 timestamp — sortable, unambiguous, Docker-friendly.
        structlog.processors.TimeStamper(fmt="iso"),
        # 4. Capture and format exceptions inline in the JSON record so stack
        #    traces appear as a structured field rather than a separate line.
        structlog.processors.format_exc_info,
        # 5. Ensure all values are JSON-serialisable (converts non-primitives
        #    to their repr so the JSONRenderer never raises).
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=shared_processors + [
            # Final step: render the event dict to a JSON string for stdout.
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    _configured = True


# ---------------------------------------------------------------------------
# Module-level logger singleton.
#
# Other modules import this and optionally bind sub-context:
#
#     from app.observability.logging_config import logger
#     log = logger.bind(component="ingestion", repo_id=repo_id)
#     log.info("clone_started", size_mb=size)
# ---------------------------------------------------------------------------
logger = structlog.get_logger()
