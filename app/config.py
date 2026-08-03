# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/config.py
-------------
Centralised configuration for the codenavigator.

Usage
-----
    from app.config import settings

    print(settings.LLM_PROVIDER)     # str
    print(settings.MAX_REPO_SIZE_MB) # int

Rules
-----
* This is the ONLY place in the codebase that reads environment variables.
* All other modules must import `settings` — never call os.getenv directly.
* The module raises at import-time if a required value is missing so that
  misconfiguration surfaces immediately rather than as a cryptic runtime error.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Typed, read-only view of all runtime configuration values."""
    
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # ── LLM / Provider ──────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["groq", "ollama"] = Field(
        default="groq", description="LLM provider to use"
    )
    GROQ_API_KEY: Optional[str] = Field(
        default=None, description="API key for Groq"
    )
    LLM_MODEL: str = Field(
        default="llama-3.1-8b-instant", description="LLM model name for FINALIZE"
    )
    DECIDE_LLM_MODEL: str = Field(
        default="llama-3.1-8b-instant",
        description="Fast model for DECIDE yes/no classification",
    )
    GROQ_HTTP_TIMEOUT_S: float = Field(
        default=20.0,
        description="Per-request HTTP timeout for Groq SDK (with max_retries=0)",
    )
    GROQ_TTFT_TIMEOUT_S: float = Field(
        default=15.0,
        description="Streaming time-to-first-token ceiling",
    )
    GROQ_DECIDE_TIMEOUT_S: float = Field(
        default=15.0,
        description="Wall-clock ceiling for DECIDE streaming calls",
    )
    GROQ_FINALIZE_TIMEOUT_S: float = Field(
        default=45.0,
        description="Wall-clock ceiling for FINALIZE streaming calls",
    )
    GROQ_LLM_RATE_LIMIT_ATTEMPTS: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Max Groq attempts per loop call when rate-limited (with backoff)",
    )
    CLAIM_EMBED_THRESHOLD: float = Field(
        default=0.40,
        description="Min embedding cosine similarity for claim↔cited-text support",
    )
    CLAIM_LEXICAL_THRESHOLD: float = Field(
        default=0.18,
        description="Min token-overlap ratio when embedding score is below threshold",
    )
    CLAIM_VERIFY_LLM_BATCH: bool = Field(
        default=False,
        description="Use a single batched LLM call for borderline claim verification",
    )
    CONTEXT_MAX_TOKENS: int = Field(
        default=5000,
        description="Hard cap on retrieval context tokens for DECIDE/FINALIZE",
    )
    EVAL_JUDGE_MODEL: Optional[str] = Field(
        default=None,
        description="RAGAS judge model (defaults to LLM_MODEL; use 8b instant for free tier)",
    )
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434", description="Base URL for local Ollama"
    )

    # ── Security ─────────────────────────────────────────────────────────────
    API_KEY: str = Field(default="dev_api_key_change_in_production", description="API Key for endpoints")
    ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
        description="Allowed CORS origins"
    )

    # ── Infrastructure ───────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis broker URL")
    REDIS_ENABLED: bool = Field(default=True, description="Try Redis for jobs/cache; fallback if down")
    REDIS_CONNECT_TIMEOUT_S: float = Field(default=1.5, description="Redis connect timeout")
    REDIS_EVAL_JOB_TTL_SECONDS: int = Field(default=604800, description="Eval job TTL in Redis (7 days)")
    REDIS_TOOL_CACHE_TTL_SECONDS: int = Field(default=3600, description="Tool cache TTL in Redis")
    ENVIRONMENT: str = Field(default="development", description="development | staging | production")

    # ── Observability ────────────────────────────────────────────────────────
    OTEL_ENDPOINT: Optional[str] = Field(default=None, description="OpenTelemetry collector endpoint")
    SENTRY_DSN: Optional[str] = Field(default=None, description="Sentry DSN for exception tracking")

    # ── Webhook ──────────────────────────────────────────────────────────────
    GITHUB_WEBHOOK_SECRET: Optional[str] = Field(
        default=None, description="Secret for verifying GitHub webhooks"
    )
    # Alias for document compatibility
    WEBHOOK_SECRET: Optional[str] = Field(
        default=None, description="Secret for verifying GitHub webhooks (alias)"
    )
    WEBHOOK_SECRET_REQUIRED: bool = Field(
        default=False,
        description="When true (or ENVIRONMENT=production), require a webhook secret",
    )
    WEBHOOK_DELIVERY_TTL_SECONDS: int = Field(
        default=86400, description="Dedup window for X-GitHub-Delivery ids"
    )
    WEBHOOK_RATE_LIMIT: str = Field(default="60/minute", description="Rate limit for /webhook/github")

    # ── Persistence paths ────────────────────────────────────────────────────
    DATA_PATH: str = Field(default="./data")
    CHROMA_DB_PATH: str = Field(default="./data/chroma_db")
    BM25_INDEX_PATH: str = Field(default="./bm25_index")
    GRAPH_STORE_PATH: str = Field(default="./data/graph_store")
    REPOS_PATH: str = Field(default="./data/repos")
    
    # ── Remote DB (Docker) ───────────────────────────────────────────────────
    CHROMA_HOST: Optional[str] = Field(default=None, description="Host for remote ChromaDB (e.g., 'chromadb')")
    CHROMA_PORT: int = Field(default=8000, description="Port for remote ChromaDB")

    # ── Ingestion ────────────────────────────────────────────────────────────
    MAX_REPO_SIZE_MB: int = Field(default=500)
    CHUNK_MAX_TOKENS: int = Field(default=2000)
    CHUNK_OVERLAP_TOKENS: int = Field(default=100)

    # ── Embedding & retrieval ────────────────────────────────────────────────
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2")
    CROSS_ENCODER_MODEL: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    ENABLE_RERANKER: bool = Field(default=True)
    RRF_K: int = Field(default=60)
    QUERY_EXPANSION_ENABLED: bool = Field(default=True)
    MIN_CONFIDENCE_SCORE: float = Field(
        default=4.0,
        validation_alias=AliasChoices("MIN_CONFIDENCE_SCORE", "CONFIDENCE_GATE_THRESHOLD"),
    )
    MAX_QUESTION_LENGTH: int = Field(default=2000)

    # ── Semantic cache ───────────────────────────────────────────────────────
    SEMANTIC_CACHE_ENABLED: bool = Field(default=True)
    CACHE_SIMILARITY_THRESHOLD: float = Field(
        default=0.95,
        validation_alias=AliasChoices(
            "CACHE_SIMILARITY_THRESHOLD", "SEMANTIC_CACHE_SIMILARITY_THRESHOLD"
        ),
    )
    SEMANTIC_CACHE_TTL_DAYS: int = Field(default=7)

    # ── Agent ────────────────────────────────────────────────────────────────
    # Budgets are deliberately tight: with warm models, most code questions
    # resolve in 1-2 searches. A high iteration/wall-clock cap just lets a slow
    # run drag on instead of failing fast. Override via .env if needed.
    MAX_AGENT_ITERATIONS: int = Field(default=3)
    # Spec-canonical alias — loop.py reads MAX_ITERATIONS; both refer to the
    # same setting so they always stay in sync.
    MAX_ITERATIONS: int = Field(
        default=3,
        validation_alias=AliasChoices("MAX_ITERATIONS", "MAX_AGENT_ITERATIONS"),
        description="Hard cap on agent loop iterations (used by loop.py)",
    )
    AGENT_MAX_SECONDS: int = Field(
        default=10000,
        description=(
            "Hard wall-clock budget for POST /chat agent runs (seconds). "
            "Exceeded +' partial answer if available, else 504."
        ),
    )
    AGENT_MAX_CUMULATIVE_RATE_LIMIT_SLEEP_S: float = Field(
        default=10000.0,
        description="Maximum total time the agent will sleep for LLM rate limits in a single session",
    )
    RETRIEVAL_FAST_PATH_SCORE: float = Field(
        default=0.25,
        description="Skip DECIDE LLM when best rerank score exceeds this",
    )
    MAX_QUERY_VARIANTS: int = Field(
        default=4,
        description="Max hybrid-search variants per ACT pass",
    )
    MAX_TOOL_CALLS: int = Field(default=3)
    MAX_TOTAL_TOKENS: int = Field(default=6000)
    EXACT_QUESTION_CACHE_TTL_S: float = Field(
        default=300.0,
        description="TTL for in-process exact-question replay cache (seconds)",
    )
    GROQ_FINALIZE_MAX_INPUT_TOKENS: int = Field(
        default=4800,
        description=(
            "Max estimated input tokens for FINALIZE (system+user). "
            "Groq free tier llama-3.1-8b-instant TPM per request is 6000."
        ),
    )
    FINALIZE_CONTEXT_MAX_TOKENS: int = Field(
        default=2500,
        description="Retrieval context token budget inside the FINALIZE user prompt",
    )
    FINALIZE_MAX_TOKENS: int = Field(
        default=1200,
        description="Max output tokens for FINALIZE Groq call (structured JSON claims)",
    )
    FINALIZE_MAX_CLAIMS: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Max claims requested in FINALIZE JSON to avoid truncation",
    )
    GROQ_LLM_TEMPERATURE: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="LLM sampling temperature — 0 for deterministic factual answers",
    )
    ENTITY_RETRIEVAL_MAX_CHUNKS: int = Field(
        default=12,
        ge=1,
        le=30,
        description="Max entity-level chunks merged for class/function questions",
    )
    DECIDE_MAX_TOKENS: int = Field(
        default=8,
        description="Max output tokens for DECIDE yes/no call",
    )
    HYBRID_SEARCH_TOP_K: int = Field(
        default=20,
        ge=1,
        le=200,
        description="top_k passed to hybrid search per query variant",
    )
    RERANK_TOP_N: int = Field(
        default=10,
        ge=1,
        le=50,
        description="top_n chunks kept after cross-encoder rerank",
    )
    LLM_RATE_LIMIT_MAX_BACKOFF_S: float = Field(
        default=12.0,
        description="Per-429 ceiling for retry-after sleep in agent loop (seconds)",
    )
    GRAPH_CONTEXT_MAX_CHARS: int = Field(
        default=2000,
        description="Max chars of graph context injected into assembled context",
    )
    CONTEXT_BUDGET_MIN_CHARS: int = Field(default=500)
    CONTEXT_TRUNCATE_REMAINING_CHARS: int = Field(default=80)

    # ── Claim verification ───────────────────────────────────────────────────
    CLAIM_EMBED_BORDERLINE_MARGIN: float = Field(
        default=0.08,
        description="Embedding score band below threshold that triggers LLM verify",
    )
    CITED_TEXT_MAX_CHARS: int = Field(
        default=4000,
        description="Max chars of cited source text for claim verification",
    )

    # ── Rate limits ──────────────────────────────────────────────────────────
    RATE_LIMIT_WINDOW_S: int = Field(
        default=60,
        ge=1,
        description="Sliding window for per-org API rate limits (seconds)",
    )
    RATE_LIMIT_CHAT_PER_MINUTE: int = Field(default=10, ge=1)
    RATE_LIMIT_INGEST_PER_MINUTE: int = Field(default=3, ge=1)
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=60, ge=1)

    # ── Frontend / scripts ───────────────────────────────────────────────────
    API_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Backend base URL for diagnostic scripts",
    )

    # ── Ingestion file filter ────────────────────────────────────────────────
    MAX_FILE_SIZE_BYTES: int = Field(default=1_048_576, description="1 MB per-file ingest cap")
    BINARY_SNIFF_BYTES: int = Field(default=8192)
    MAX_MEAN_LINE_LENGTH: int = Field(default=300)
    MAX_REPLACEMENT_CHAR_RATIO: float = Field(default=0.05, ge=0.0, le=1.0)

    # ── SSE streaming ────────────────────────────────────────────────────────
    SSE_QUEUE_MAXSIZE: int = Field(default=64, ge=1)
    SSE_QUEUE_GET_TIMEOUT_S: float = Field(default=1.0, ge=0.1)
    SSE_STREAM_IDLE_TIMEOUT_S: float = Field(default=300.0, ge=10.0)

    # ── Eval / regression ──────────────────────────────────────────────────
    EVAL_MAX_QUESTIONS: int = Field(default=0, description="0 = run all golden questions")
    EVAL_SKIP_AGENT_PROBE: bool = Field(default=True)
    EVAL_VERSION: Optional[str] = Field(default=None)
    EVAL_QUESTION_DELAY_S: float = Field(default=4.0, ge=0.0)
    EVAL_JOB_MAX_SECONDS: int = Field(
        default=1800,
        ge=120,
        description="Wall-clock cap for async RAGAS/Golden eval background jobs",
    )
    EVAL_STATE_PATH_RUNS: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Repeated agent runs per golden question for state-path consistency",
    )
    EVAL_RAGAS_TIMEOUT_S: int = Field(
        default=300,
        ge=60,
        description="Per-metric RAGAS judge timeout (seconds)",
    )

    # ── Graph ────────────────────────────────────────────────────────────────
    MAX_GRAPH_NODES: int = Field(default=10_000)
    GRAPH_SUBGRAPH_MAX_FANOUT: int = Field(
        default=15,
        ge=3,
        le=50,
        description="Max direct callers/callees shown per node in call-graph diagrams",
    )
    GRAPH_SUBGRAPH_MAX_NODES: int = Field(
        default=20,
        ge=5,
        le=60,
        description="Max nodes rendered in a single Mermaid diagram",
    )
    DIAGRAM_DEFAULT_DIRECTION: str = Field(
        default="downstream",
        description="Default call-graph traversal: upstream, downstream, or both",
    )
    CYCLE_DETECTION_TIMEOUT_S: int = Field(default=10)

    # ── Ingestion queue ──────────────────────────────────────────────────────
    INGEST_PENDING_TTL_SECONDS: int = Field(default=900)

    # ── External calls ───────────────────────────────────────────────────────
    SEARCH_WEB_DOCS_TIMEOUT_S: int = Field(default=5)

    # ── Context compression ──────────────────────────────────────────────────
    CONTEXT_COMPRESSION_THRESHOLD: float = Field(default=0.6)

    # ── Observability ────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")

    # ── Multi-tenant quotas (0 = unlimited) ───────────────────────────────────
    QUOTA_CHAT_PER_MONTH: int = Field(default=0, description="Max chat requests per org per month")
    QUOTA_INGEST_PER_MONTH: int = Field(default=0, description="Max ingest jobs per org per month")
    QUOTA_EVAL_PER_MONTH: int = Field(default=0, description="Max eval runs per org per month")
    PROTECT_METRICS: bool = Field(default=True, description="Require API key for /metrics in production")
    DISABLE_OPENAPI_IN_PRODUCTION: bool = Field(default=True, description="Hide /docs in production")

    # ── Stripe billing ────────────────────────────────────────────────────────
    STRIPE_SECRET_KEY: Optional[str] = Field(default=None, description="Stripe secret key")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None, description="Stripe webhook signing secret")
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(default=None, description="Stripe publishable key for admin UI")
    STRIPE_PRICE_PRO: Optional[str] = Field(default=None, description="Stripe Price ID for Pro plan")
    STRIPE_PRICE_TEAM: Optional[str] = Field(default=None, description="Stripe Price ID for Team plan")

    # ── GitHub App / token ───────────────────────────────────────────────────
    GITHUB_TOKEN: Optional[str] = Field(default=None, description="PAT for private repo clone fallback")
    GITHUB_APP_ID: Optional[str] = Field(default=None, description="GitHub App ID")
    GITHUB_APP_PRIVATE_KEY: Optional[str] = Field(default=None, description="GitHub App PEM private key")

    # ── OIDC SSO ─────────────────────────────────────────────────────────────
    OIDC_CLIENT_ID: Optional[str] = Field(default=None)
    OIDC_CLIENT_SECRET: Optional[str] = Field(default=None)
    OIDC_ISSUER_URL: Optional[str] = Field(default=None, description="e.g. https://accounts.google.com")
    OIDC_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/callback")
    OIDC_POST_LOGIN_REDIRECT: str = Field(default="http://localhost:3000")
    OIDC_SCOPES: str = Field(default="openid email profile")
    OIDC_ALLOW_UNSIGNED: bool = Field(
        default=False,
        description="Dev only: skip ID token signature verify when true",
    )
    SESSION_SECRET: Optional[str] = Field(default=None, description="JWT session signing secret")
    SESSION_TTL_SECONDS: int = Field(default=86400, description="Session TTL (24h)")

    # ── Platform persistence (Phase B) ───────────────────────────────────────
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL URL for platform state (optional; JSON fallback if unset)",
    )

    # ── Enterprise SAML (Phase C) ─────────────────────────────────────────────
    SAML_ENABLED: bool = Field(default=False)
    SAML_IDP_METADATA_URL: Optional[str] = Field(default=None)
    SAML_SP_ENTITY_ID: Optional[str] = Field(default=None)
    SAML_ACS_URL: Optional[str] = Field(default=None)

    def effective_webhook_secret(self) -> str | None:
        """GITHUB_WEBHOOK_SECRET with WEBHOOK_SECRET alias fallback."""
        for val in (self.GITHUB_WEBHOOK_SECRET, self.WEBHOOK_SECRET):
            if val and str(val).strip():
                return str(val).strip()
        return None

    @model_validator(mode="after")
    def validate_secrets(self) -> 'Settings':
        """
        Raise immediately at import time if a fatal configuration error is detected.
        """
        if self.LLM_PROVIDER == "groq" and not (self.GROQ_API_KEY and self.GROQ_API_KEY.strip()):
            raise ValueError(
                "\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  CONFIG ERROR — missing GROQ_API_KEY                         ║\n"
                "╠══════════════════════════════════════════════════════════════╣\n"
                "║  LLM_PROVIDER is set to 'groq' but GROQ_API_KEY is empty.    ║\n"
                "║                                                              ║\n"
                "║  Fix:  add your key to the .env file:                        ║\n"
                "║        GROQ_API_KEY=gsk_...                                  ║\n"
                "║                                                              ║\n"
                "║  Get a free key at: https://console.groq.com/keys            ║\n"
                "╚══════════════════════════════════════════════════════════════╝\n"
            )

        require_webhook = self.WEBHOOK_SECRET_REQUIRED or self.ENVIRONMENT.lower() == "production"
        if require_webhook and not self.effective_webhook_secret():
            raise ValueError(
                "\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  CONFIG ERROR — missing GITHUB_WEBHOOK_SECRET                ║\n"
                "╠══════════════════════════════════════════════════════════════╣\n"
                "║  Webhook secret is required in production. Set:              ║\n"
                "║        GITHUB_WEBHOOK_SECRET=<from GitHub webhook settings>  ║\n"
                "║  Or set ENVIRONMENT=development for local runs.                ║\n"
                "╚══════════════════════════════════════════════════════════════╝\n"
            )

        if self.ENVIRONMENT.lower() == "production":
            from app.platform.api_keys import is_production_api_key_valid

            if not is_production_api_key_valid():
                raise ValueError(
                    "\n"
                    "╔══════════════════════════════════════════════════════════════╗\n"
                    "║  CONFIG ERROR — weak API_KEY in production                   ║\n"
                    "╠══════════════════════════════════════════════════════════════╣\n"
                    "║  Set a strong API_KEY (24+ chars, not dev-secret-key).       ║\n"
                    "║  Or use data/api_keys.json for per-org keys.                   ║\n"
                    "╚══════════════════════════════════════════════════════════════╝\n"
                )
        return self


# ---------------------------------------------------------------------------
# Singleton accessor — lru_cache ensures the Settings object is constructed
# exactly once per process, never per request (Pydantic validation fires here).
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the process-wide Settings singleton.

    All modules should import this function (or the pre-built `settings`
    alias below) rather than constructing their own Settings() instance.
    Using lru_cache guarantees a single construction + validation per
    process lifetime, even if the function is called from multiple threads.
    """
    return Settings()


# Convenience alias so existing code can keep `from app.config import settings`
# without modification, while new code can call get_settings() explicitly.
settings: Settings = get_settings()
