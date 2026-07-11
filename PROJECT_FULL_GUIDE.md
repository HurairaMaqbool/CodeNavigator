# CodeNavigator — Complete Project Guide

> **Product name:** CodeNavigator (branded in UI)  
> **Repository folder:** `codebase-onboarding-agent`  
> **Author:** Huraira Maqbool  
> **Stack:** Python 3.12 · FastAPI · ChromaDB · BM25 · NetworkX · Groq/Ollama · Next.js 16 · Streamlit

This document is the **single reference** for everything in the project: every major module, pipeline stage, API endpoint, frontend route, data store, configuration knob, and operational workflow. Read this file top-to-bottom to understand the full system without opening the codebase.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [System Architecture](#2-system-architecture)
3. [Repository Layout](#3-repository-layout)
4. [Backend — FastAPI Application (`app/`)](#4-backend--fastapi-application-app)
5. [Ingestion Pipeline (End-to-End)](#5-ingestion-pipeline-end-to-end)
6. [Retrieval & Indexing Layer](#6-retrieval--indexing-layer)
7. [Call Graph Engine](#7-call-graph-engine)
8. [Agentic RAG Chat Loop](#8-agentic-rag-chat-loop)
9. [Hallucination Guard & Safety](#9-hallucination-guard--safety)
10. [Evaluation & Quality Assurance (`eval/`)](#10-evaluation--quality-assurance-eval)
11. [Platform, Billing & Multi-Tenancy](#11-platform-billing--multi-tenancy)
12. [Webhooks & Integrations](#12-webhooks--integrations)
13. [Complete API Reference](#13-complete-api-reference)
14. [Frontends](#14-frontends)
15. [Data Stores & Persistence](#15-data-stores--persistence)
16. [Configuration & Environment](#16-configuration--environment)
17. [How to Run Locally](#17-how-to-run-locally)
18. [Testing](#18-testing)
19. [Scripts & Diagnostics](#19-scripts--diagnostics)
20. [Deployment & CI/CD](#20-deployment--cicd)
21. [Key Design Decisions](#21-key-design-decisions)
22. [Related Documentation Files](#22-related-documentation-files)

---

## 1. What This Project Does

**Problem:** Onboarding onto a new codebase takes days. Developers grep files, trace call chains manually, read stale docs, and interrupt senior engineers.

**Solution:** CodeNavigator ingests any public (or GitHub App–connected private) Git repository, builds three complementary indexes, and exposes an autonomous agent that answers architecture questions with **verified file:line citations**. It also generates Mermaid call-graph diagrams, runs automated RAGAS evaluations, and supports commercial platform features (usage metering, billing, audit logs, SSO).

### Core capabilities

| Capability | Description |
|------------|-------------|
| **Repository ingestion** | Clone → filter → AST parse → chunk → triple-index (vector + BM25 + graph) |
| **Agentic chat** | LLM-driven tool loop: hybrid search, file read, graph traversal, diagrams |
| **Citation verification** | Every answer is scored; low-confidence responses are gated |
| **Semantic caching** | Near-duplicate questions served from cache (commit-scoped) |
| **Call-graph diagrams** | Mermaid output for any symbol, with depth control |
| **Auto-sync** | GitHub webhooks re-ingest on push; cache invalidated |
| **RAGAS evaluation** | Faithfulness, relevancy, precision, recall on golden set |
| **Golden-set CI** | Post-ingest regression check against fixed Q&A corpus |
| **Platform admin** | Usage quotas, Stripe billing, audit trail, API keys, GDPR purge |

### Who talks to whom

```
Developer / GitHub Webhook
        │
        ▼
┌───────────────────┐     ┌───────────────────┐
│  Next.js UI       │     │  Streamlit UI     │  (legacy, still present)
│  localhost:3000   │     │  localhost:8501   │
└─────────┬─────────┘     └─────────┬─────────┘
          │  HTTP + X-API-Key       │
          └───────────┬─────────────┘
                      ▼
          ┌───────────────────────┐
          │  FastAPI Backend      │
          │  localhost:8000       │
          └───────────┬───────────┘
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
 ChromaDB          BM25 pickle      NetworkX graph
 (vectors)         (keyword)        (call graph)
     │                │                │
     └────────────────┴────────────────┘
                      │
              Redis (optional)
         Celery worker (optional)
         PostgreSQL (optional)
```

---

## 2. System Architecture

### 2.1 Layered view

| Layer | Location | Responsibility |
|-------|----------|----------------|
| **Presentation** | `frontend-next/`, `frontend/`, `admin/` | User interfaces |
| **API gateway** | `app/api/`, `app/main.py` | REST, SSE, auth, rate limits |
| **Agent** | `app/agent/` | RAG reasoning loop, tools, caching, gating |
| **Retrieval** | `app/retrieval/` | Embeddings, Chroma, BM25, hybrid fusion, rerank |
| **Graph** | `app/graph/`, `app/diagrams/` | Call graph build + BFS queries + Mermaid |
| **Ingestion** | `app/ingestion/`, `app/parsing/`, `app/tasks/` | Clone, parse, chunk, index |
| **Evaluation** | `eval/`, `app/evaluation/` | RAGAS runner, golden CI, compare |
| **Platform** | `app/platform/`, `app/api/billing_router.py` | Tenancy, quotas, billing, audit |
| **Infrastructure** | `app/config.py`, Redis, PG, Docker, `k8s/` | Config, queues, persistence, deploy |

### 2.2 Ingestion state machine

Defined in `app/ingestion/metadata_store.py`:

```
PENDING → CLONING → FILTERING → PARSING → INDEXING → SYNCED
                                              │
                                         (any stage) → FAILED
```

The UI stepper maps these to: **Clone → Filter → Parse → Chunk → Index → Synced** (`frontend-next/lib/constants.ts` → `INGEST_STEPS`).

### 2.3 Agent state machine

Defined in `app/agent/loop.py`:

```
INTAKE → PLAN → ACT → OBSERVE → DECIDE → FINALIZE → VERIFY → RESPOND
         ↑__________________________________|  (loop until cap or DECIDE=no)
```

Live progress is streamed via SSE: `GET /chat/stream/{session_id}`.

---

## 3. Repository Layout

```
codebase-onboarding-agent/
│
├── app/                        # ★ FastAPI backend (all core logic)
├── eval/                       # ★ RAGAS + golden-set evaluation CLI
├── tests/                      # Pytest suite (~70 modules, 550+ tests)
│
├── frontend-next/              # ★ Primary modern UI (Next.js 16)
├── frontend/                   # Legacy Streamlit UI
├── admin/                      # Vite/React admin dashboard
│
├── scripts/                    # Operational Python diagnostics
├── scratch/                    # Ad-hoc verification scripts & build logs
├── data/                       # Runtime data (repos, sessions, golden set)
├── eval_results/               # Eval run JSON artifacts
├── docs/                       # Deployment, legal, commercial docs
├── k8s/                        # Kubernetes manifests
├── .github/workflows/          # CI (pytest) + eval workflow
│
├── README.md                   # Marketing + quick start
├── PROJECT_OVERVIEW.md         # Shorter architecture overview
├── PROJECT_BLUEPRINT.md        # Build blueprint
├── MODULES.md                    # Module build-order reference
├── PROJECT_FULL_GUIDE.md       # ★ This file
│
├── requirements.txt              # Python dependencies
├── requirements-docker.txt
├── requirements-eval.txt
├── requirements-heavy.txt
├── .env.example                # Environment template
├── pytest.ini
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── run_local.bat               # Start backend + Streamlit
└── start.bat
```

---

## 4. Backend — FastAPI Application (`app/`)

The backend is organized into ~15 sub-packages. Below is **every major module** with its role.

### 4.1 Bootstrap & infrastructure

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI factory, lifespan, CORS, rate-limit handler, router mounts, `/health`, `/metrics`, model warm-up |
| `app/config.py` | Pydantic `Settings` — single source of truth for all environment variables |
| `app/paths.py` | Helpers resolving paths under `DATA_PATH` |
| `app/chroma_client.py` | ChromaDB client factory; disables telemetry |
| `app/redis_client.py` | Lazy Redis client with graceful fallback when Redis is down |
| `app/repo_resolver.py` | Resolves `job_id` → `asset_repo_id` via alias files |
| `app/debug_trace.py` | Optional session debug logging to disk |

### 4.2 API layer (`app/api/`)

| File | Purpose |
|------|---------|
| `router.py` | **Core REST API** — ingest, status, chat, diagram, onboarding-path, eval endpoints |
| `auth.py` | `X-API-Key` validation + OIDC session cookies; binds request to `org_id` |
| `rate_limiter.py` | SlowAPI sliding-window limits (`/ingest` 3/min, `/chat` 10/min) |
| `status_router.py` | Public unauthenticated `/status/public` uptime page |
| `platform_router.py` | GDPR purge/export, audit log, usage, API keys, GitHub installations |
| `billing_router.py` | Stripe plans, checkout, portal, subscription status |
| `sso_router.py` | OIDC login/callback/logout/me/status under `/auth/*` |
| `saml_router.py` | Enterprise SAML metadata/login under `/saml/*` |
| `state_stream.py` | SSE stream of agent state transitions per chat session |

### 4.3 Ingestion (`app/ingestion/`)

| File | Purpose |
|------|---------|
| `clone.py` | Git shallow clone; derives `repo_id`; offline dummy-repo fallback; size limits |
| `file_filter.py` | Walk repo tree; allowlist `.py`/`.js`/`.ts`; reject binaries/minified files |
| `metadata_store.py` | Per-repo JSON state machine (`Stage` enum); alias mapping; atomic writes |
| `locking.py` | Per-`repo_id` file + thread locks — prevents concurrent ingestion |
| `repo_readiness.py` | **Single source of truth** for "is repo ready for chat/eval?" — handles job↔asset aliases |
| `language_registry.py` | File extension → Tree-sitter language mapping |
| `path_normalize.py` | Canonical repo-relative path normalization |
| `progress_counts.py` | Shared files/chunks counters for `/status` responses |

### 4.4 Parsing (`app/parsing/`)

| File | Purpose |
|------|---------|
| `tree_sitter_parser.py` | AST extraction: classes, functions, imports, docstrings |
| `chunker.py` | Splits parsed files at function/class boundaries — never mid-logic |

### 4.5 Retrieval (`app/retrieval/`)

| File | Purpose |
|------|---------|
| `embeddings.py` | SentenceTransformers embed + batch embed |
| `vector_store.py` | ChromaDB per-repo collections; query; embedding-model mismatch guard |
| `bm25_store.py` | `rank_bm25` pickle index per repo |
| `hybrid_search.py` | Vector + BM25 fused via Reciprocal Rank Fusion (RRF) |
| `reranker.py` | Cross-encoder reranking of top-K results |
| `query_expansion.py` | Heuristic + LLM query expansion before search |

### 4.6 Graph (`app/graph/`)

| File | Purpose |
|------|---------|
| `builder.py` | Builds NetworkX `DiGraph` from parsed imports + calls → `graph.json` |
| `queries.py` | Timeout-safe BFS for callers/callees (configurable hop limit) |

### 4.7 Diagrams (`app/diagrams/`)

| File | Purpose |
|------|---------|
| `mermaid_generator.py` | Subgraph → Mermaid markdown; handles empty graphs (`no_connections`) |

### 4.8 Agent (`app/agent/`)

| File | Purpose |
|------|---------|
| `loop.py` | Core state-machine agent loop (INTAKE→…→RESPOND) |
| `tools.py` | Tool JSON schemas + execution for all agent tools |
| `llm_client.py` | Groq / Ollama provider abstraction |
| `system_prompt.py` | Canonical system prompt + `PROMPT_VERSION` |
| `semantic_cache.py` | Chroma-backed semantic answer cache (~95% similarity, commit-scoped) |
| `context_manager.py` | Token budget monitoring; compresses old tool results |
| `confidence.py` | Citation validation; confidence scoring; gating threshold |
| `claim_verification.py` | Atomic claim ↔ cited-text verification |
| `grounding.py` | Structured FINALIZE JSON output contract |
| `onboarding_path.py` | Personalized learning-path generator for new developers |
| `retrieval_prefetch.py` | Symbol-boosted multi-hop retrieval prefetch |
| `symbol_lookup.py` | Resolve symbols to authoritative file:line via BM25 |
| `citation_repair.py` | Post-process answers: fix/strip bad citations |
| `response_firewall.py` | Sanitize user-visible text (strip tool leaks) |
| `cache_keys.py` | Normalized cache keys for tool calls |
| `prompts/plan_prompt.py` | PLAN state prompt |
| `prompts/decide_prompt.py` | DECIDE yes/no prompt |
| `prompts/finalize_prompt.py` | FINALIZE grounded-answer prompt |
| `prompts/compress_prompt.py` | OBSERVE compression prompt |

#### Agent tools (`tools.py`)

| Tool | What it does |
|------|--------------|
| `search_code` | Hybrid semantic + keyword search with RRF + rerank |
| `read_file` | Raw file contents (path-jailed to clone root) |
| `get_callers` | Graph BFS upstream — who calls this function |
| `get_callees` | Graph BFS downstream — what this function calls |
| `generate_diagram` | Mermaid call-graph for a symbol |
| `search_web_docs` | Legacy external docs search |
| `get_subgraph` | Legacy graph traversal helper |

### 4.9 Background tasks (`app/tasks/`)

| File | Purpose |
|------|---------|
| `celery_app.py` | Celery app config; Redis broker; `ingestion` queue |
| `ingestion_task.py` | `run_ingestion_sync()` — full pipeline; Celery task wrapper |

### 4.10 Jobs (`app/jobs/`)

| File | Purpose |
|------|---------|
| `eval_job_store.py` | Eval job state: Redis + disk + in-process cache |

### 4.11 Cache (`app/cache/`)

| File | Purpose |
|------|---------|
| `tool_cache.py` | Redis L2 + in-process L1 cache for tool results |

### 4.12 Webhooks (`app/webhook/`)

| File | Purpose |
|------|---------|
| `github_webhook.py` | HMAC-verified GitHub push → re-ingest |
| `github_app_webhook.py` | GitHub App installation/push events |
| `stripe_webhook.py` | Stripe subscription lifecycle events |
| `delivery_guard.py` | Webhook delivery idempotency (Redis or in-memory) |

### 4.13 Authentication (`app/auth/`)

| File | Purpose |
|------|---------|
| `oidc.py` | OIDC login flow; session JWT in cookie |
| `oidc_jwks.py` | JWKS fetch + ID token verification |
| `oauth_state.py` | OAuth CSRF state storage (Redis fallback) |

### 4.14 GitHub App (`app/integrations/github_app/`)

| File | Purpose |
|------|---------|
| `auth.py` | GitHub App JWT + installation access tokens |
| `clone_auth.py` | Resolve clone credentials (App token or PAT) |
| `installations.py` | Installation → `org_id` mapping |

### 4.15 Platform (`app/platform/`)

| File | Purpose |
|------|---------|
| `tenant_context.py` | Request-scoped `org_id` via Python `contextvars` |
| `api_keys.py` | Multi-tenant API key registry (create/list/revoke) |
| `audit_log.py` | Append-only audit trail |
| `usage_meter.py` | Per-org usage counters + quota enforcement |
| `repo_purge.py` | GDPR purge: clone, vectors, BM25, graph, cache, metadata |
| `billing/plans.py` | Plan tiers (free/pro/team) + monthly quotas |
| `billing/subscriptions.py` | Org subscription state |
| `billing/stripe_client.py` | Stripe checkout/portal/webhook helpers |
| `db/connection.py` | PostgreSQL connection pool |
| `db/postgres.py` | Schema bootstrap + health check |
| `db/stores.py` | PG-backed platform persistence (JSON fallback if PG unset) |

### 4.16 Security (`app/security/`)

| File | Purpose |
|------|---------|
| `path_jail.py` | Ensures file reads stay inside the cloned repo root |

### 4.17 Observability (`app/observability/`)

| File | Purpose |
|------|---------|
| `logging_config.py` | structlog JSON logging configuration |
| `tracing.py` | OpenTelemetry setup (optional) |

### 4.18 Legacy evaluation harness (`app/evaluation/`)

Parallel to the `eval/` package — older dashboard harness:

| File | Purpose |
|------|---------|
| `run_eval.py` | RAGAS dashboard harness vs `tests/eval_set.json` |
| `ragas_providers.py` | Free-tier RAGAS LLM/embed wrappers |
| `compare_runs.py` | Eval run history comparison |

---

## 5. Ingestion Pipeline (End-to-End)

### 5.1 Trigger

Ingestion starts via:

- `POST /ingest` from UI (Next.js or Streamlit)
- `POST /webhook/github` on push events
- `POST /webhook/github-app` for GitHub App events

### 5.2 API pre-flight (`router.py`)

1. Validate `repo_url` (Pydantic `HttpUrl`)
2. Check embedding model mismatch → HTTP 409 if re-index required
3. Acquire per-repo write lock (`locking.py`)
4. Check monthly ingest quota (`usage_meter.py`)
5. `metadata_store.mark_pending()`
6. Dispatch:
   - **Celery** `run_ingestion.delay()` if Redis + worker available
   - **Else** FastAPI `BackgroundTasks` → `run_ingestion_sync()`
7. Return **202 Accepted** `{ job_id, status: "processing" }`

### 5.3 Pipeline steps (`run_ingestion_sync` in `ingestion_task.py`)

| Step | Stage | Module | Output |
|------|-------|--------|--------|
| 1 | CLONING | `clone.py` | Git working tree under `data/repos/{repo_id}/clone/` |
| 2 | FILTERING | `file_filter.py` | List of safe, supported source files |
| 3 | PARSING | `tree_sitter_parser.py` | AST nodes per file; progress checkpoints |
| 4 | CHUNKING | `chunker.py` | Function/class-boundary text chunks |
| 5a | INDEXING | `vector_store.py` | ChromaDB embeddings per repo |
| 5b | INDEXING | `bm25_store.py` | `{BM25_INDEX_PATH}/{repo_id}/bm25.pkl` |
| 5c | INDEXING | `graph/builder.py` | `{GRAPH_STORE_PATH}/{repo_id}/graph.json` |
| 6 | SYNCED | `metadata_store.py` | `sync_status=synced`, commit hash saved |

**Alias handling:** If `job_id ≠ asset_repo_id` (URL-derived hash), an alias file links them. `repo_readiness.py` treats both as one logical repo.

**Post-sync:** Optional background thread re-runs golden-set CI (`_refresh_golden_set_async`).

### 5.4 Status polling

`GET /status/{job_id}` returns:

```json
{
  "job_id": "...",
  "repo_id": "...",
  "ref": "main",
  "commit_hash": "abc123",
  "sync_status": "synced",
  "ready": true,
  "status": "ready",
  "files_parsed": 36,
  "chunks_created": 521,
  "asset_repo_id": "...",
  "graph_truncated": false,
  "has_circular_dependencies": false,
  "error": null
}
```

**Readiness rule:** Always use `ready` / `repo_readiness.is_repo_ready()` — never check `sync_status` alone (alias pairs can diverge).

---

## 6. Retrieval & Indexing Layer

### 6.1 Triple index strategy

| Index | Technology | Best for |
|-------|------------|----------|
| **Semantic** | ChromaDB + SentenceTransformers | Conceptual / paraphrased questions |
| **Keyword** | BM25 (pickle per repo) | Exact symbol names, variables, imports |
| **Relational** | NetworkX DiGraph | Call chains, dependency tracing |

### 6.2 Hybrid search flow

```
User query
    → query_expansion.py (optional LLM synonyms)
    → Chroma vector search (top-K)
    → BM25 search (top-K)
    → hybrid_search.py: Reciprocal Rank Fusion
    → reranker.py: Cross-encoder rerank
    → return ranked chunks with file_path + line numbers
```

### 6.3 Embedding model safety

`vector_store.py` guards against embedding-model mismatch on re-ingest. If the model changed, `/ingest` with `force_reindex=true` is required (HTTP 409 otherwise).

---

## 7. Call Graph Engine

### 7.1 Graph construction (`graph/builder.py`)

- Nodes: functions, methods, modules
- Edges: `calls`, `imports`
- Stored as JSON: `data/graph_store/{repo_id}/graph.json`
- Metadata: `graph_truncated`, `has_circular_dependencies`

### 7.2 Queries (`graph/queries.py`)

- `get_subgraph(repo_id, symbol, direction, max_depth)` — BFS with timeout
- Directions: `callers`, `callees`, `both`
- Default max depth: 3 hops (configurable per request)

### 7.3 Diagram generation (`diagrams/mermaid_generator.py`)

`GET /diagram/{repo_id}/{function_name}?depth=N` returns:

```json
{
  "mermaid": "graph TD\n  ...",
  "empty": false,
  "requested_depth": 2,
  "clamped": false
}
```

Empty graphs return `empty: true`, `reason: "no_connections"`.

---

## 8. Agentic RAG Chat Loop

### 8.1 Entry point

`POST /chat` with body:

```json
{
  "repo_id": "<job_id>",
  "question": "How does Session.send work?",
  "session_id": "optional-uuid"
}
```

### 8.2 Pre-checks

1. `repo_readiness.evaluate_chat_readiness()` — refuse if not synced (HTTP 409)
2. Org access enforcement (`_enforce_repo_org`)
3. Monthly chat quota check (HTTP 429)
4. Load session history from `data/sessions/{session_id}.json` (last 10 turns)

### 8.3 State-by-state behavior

| State | What happens |
|-------|--------------|
| **INTAKE** | Exact-question cache lookup; semantic cache lookup (Chroma, commit-scoped) |
| **PLAN** | Query expansion; build retrieval plan |
| **ACT** | Execute tools (`search_code`, `read_file`, graph tools, etc.) |
| **OBSERVE** | Compress older tool results if context is large |
| **DECIDE** | LLM yes/no: need more retrieval? Fast-path if rerank score is high |
| **FINALIZE** | LLM generates grounded answer with citations |
| **VERIFY** | `confidence.py` + `claim_verification.py` — gate if score < threshold |
| **RESPOND** | `citation_repair.py` + `response_firewall.py` → cache + return |

### 8.4 Response shape

```json
{
  "answer": "...",
  "sources": [
    {
      "file_path": "requests/sessions.py",
      "function_name": "Session.send",
      "start_line": 400,
      "end_line": 450
    }
  ],
  "confidence_score": 9.1,
  "gated": false,
  "cache_hit": false,
  "trace": [{ "state": "ACT" }, { "state": "VERIFY" }]
}
```

### 8.5 Error handling surfaced to UI

| HTTP | Meaning | UI behavior |
|------|---------|---------------|
| 409 | Repo still indexing / model mismatch | "Repository is still indexing" |
| 429 | Rate limit or quota | Shows retry-after seconds |
| 504 | Groq/LLM timeout | "Request timed out" message |
| 404 | Unknown repo | Error toast |

### 8.6 Live SSE stream

`GET /chat/stream/{session_id}` emits `data: {"state":"ACT","label":"Search",...}` events. The Next.js `openChatStream()` in `lib/api.ts` consumes these for the agent step indicator.

---

## 9. Hallucination Guard & Safety

### 9.1 Confidence scoring (`confidence.py`)

1. Parse markdown citations from the LLM answer (`file:start-end`)
2. For each citation:
   - Does the file exist in the index?
   - Are line numbers within file bounds?
   - Does cited text match retrieved context?
3. Compute deterministic score 0–10
4. If score < `CONFIDENCE_GATE_THRESHOLD` (default 4.0) → `gated=true`, safe fallback answer

### 9.2 Additional safety layers

| Layer | Module | Role |
|-------|--------|------|
| Claim verification | `claim_verification.py` | Atomic claim ↔ evidence check |
| Citation repair | `citation_repair.py` | Fix or strip malformed citations |
| Response firewall | `response_firewall.py` | Remove tool-call leaks from user text |
| Path jail | `path_jail.py` | Prevent directory traversal on `read_file` |

---

## 10. Evaluation & Quality Assurance (`eval/`)

### 10.1 Package modules

| File | Purpose |
|------|---------|
| `run_eval.py` | Main RAGAS runner; orchestrates full eval suite |
| `golden_runner.py` | Golden-set CI runner (post-ingest refresh) |
| `compare_runs.py` | Regression detection across eval report versions |
| `health_check.py` | Pre-eval gates: index readiness, optional agent probe |
| `eval_store.py` | Unified eval run persistence |
| `context_builder.py` | Build RAGAS context strings from agent responses |
| `retrieval_metrics.py` | Shared retrieval scoring utilities |
| `ragas_providers.py` | Zero-cost RAGAS LLM/embed provider wrappers |
| `groq_guard.py` | Pre-flight Groq availability checks |

### 10.2 Golden set

- Corpus file: `data/golden_set.json`
- Contains question/expected-file pairs per fixture repo
- Golden CI status: `GET /eval/golden-status`

### 10.3 RAGAS eval flow

1. UI calls `POST /eval/run?repo_id=...`
2. Backend checks `eval/health_check.py` (uses `repo_readiness`)
3. Background thread runs RAGAS metrics
4. Poll `GET /eval/status/{job_id}` until `done` or `error`
5. Results stored in eval history; UI renders charts via Recharts

### 10.4 Metrics tracked

- Faithfulness
- Answer relevancy
- Context precision / recall
- Mean confidence score
- Retrieval precision@3
- Per-question diagnostics (hit, gated, top files)

### 10.5 Version compare

`POST /eval/compare` with `{ baseline_version, candidate_version, tolerance }` → regression list. The Next.js UI disables compare when both dropdowns select the same version.

---

## 11. Platform, Billing & Multi-Tenancy

### 11.1 Tenancy model

- Every API request resolves an `org_id` from API key or OIDC session
- `tenant_context.py` stores it in a contextvar
- Repos are scoped to orgs; cross-org access is denied

### 11.2 Plans & quotas (`billing/plans.py`)

| Plan | Chat/mo | Ingest/mo | Eval/mo |
|------|---------|-----------|---------|
| free | 100 | 5 | 10 |
| pro | higher | higher | higher |
| team | higher | higher | higher |

Enforced at `/ingest`, `/chat`, `/eval/run` → HTTP 429 when exceeded.

### 11.3 Audit log

Events include: `ingest.started`, `chat.completed`, `api_key.created`, `repo.purged`, etc.  
Readable via `GET /platform/audit?limit=50`.

### 11.4 GDPR

- `DELETE /platform/repos/{repo_id}` — full purge
- `GET /platform/repos/{repo_id}/export` — metadata export snapshot

### 11.5 Stripe billing

- `GET /billing/plans` — public plan list
- `POST /billing/checkout` — Stripe checkout session
- `POST /billing/portal` — customer portal
- `POST /webhook/stripe` — subscription lifecycle

### 11.6 SSO

- OIDC: `/auth/login`, `/auth/callback`, `/auth/me`
- SAML stub: `/saml/metadata`, `/saml/login`

---

## 12. Webhooks & Integrations

### GitHub push webhook

```
POST /webhook/github
  → Verify X-Hub-Signature-256 (HMAC)
  → delivery_guard dedup
  → acquire write lock
  → run_ingestion_sync(force_reindex=True)
  → invalidate semantic cache for repo
  → update commit_hash
```

### GitHub App

- Private repo clone via installation tokens
- `GET /platform/github/installations`
- `POST /webhook/github-app`

---

## 13. Complete API Reference

### 13.1 Core (`app/api/router.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | Liveness + timestamp |
| GET | `/ready` | No | Readiness: Chroma, Redis, Postgres |
| POST | `/ingest` | API key | Start background ingestion (202) |
| GET | `/status/public` | No | Public uptime page |
| GET | `/status/{job_id}` | API key | Ingestion progress + readiness |
| GET | `/chat/stream/{session_id}` | API key | SSE agent state stream |
| POST | `/chat` | API key | Agentic RAG query (10/min) |
| POST | `/diagram` | API key | Mermaid from entry point (POST body) |
| POST | `/onboarding-path` | API key | Personalized learning path |
| GET | `/diagram/{repo_id}` | API key | Diagram (query param `function_name`) |
| GET | `/diagram/{repo_id}/{function_name}` | API key | Diagram with depth query param |
| POST/GET | `/eval/run` | API key | Start async RAGAS eval |
| GET | `/eval/health/{repo_id}` | API key | Pre-eval readiness check |
| GET | `/eval/status/{job_id}` | API key | Poll eval job |
| GET | `/eval/status` | API key | Last 5 eval runs |
| GET | `/eval/history` | API key | All eval runs |
| POST/GET | `/eval/compare` | API key | Compare eval versions |
| GET | `/eval/golden-status` | API key | Golden CI status |
| POST/GET | `/eval/golden/run` | API key | Run golden set |

### 13.2 Platform (`/platform`)

| Method | Path | Purpose |
|--------|------|---------|
| DELETE | `/platform/repos/{repo_id}` | GDPR purge |
| GET | `/platform/repos/{repo_id}/export` | GDPR export |
| GET | `/platform/audit` | Audit trail |
| GET | `/platform/usage` | Usage summary |
| POST | `/platform/api-keys` | Create API key |
| GET | `/platform/api-keys` | List keys |
| DELETE | `/platform/api-keys` | Revoke key |
| GET | `/platform/github/installations` | GitHub App installs |

### 13.3 Billing (`/billing`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/billing/plans` | Public plan list |
| GET | `/billing/subscription` | Org subscription + limits |
| POST | `/billing/checkout` | Stripe checkout |
| POST | `/billing/portal` | Stripe portal |

### 13.4 Auth (`/auth`, `/saml`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/auth/login` | OIDC redirect |
| GET | `/auth/callback` | OIDC callback + session cookie |
| POST | `/auth/logout` | Clear session |
| GET | `/auth/me` | Current user |
| GET | `/auth/status` | SSO config status |
| GET | `/saml/metadata` | SP metadata |
| GET | `/saml/login` | SAML login |

### 13.5 Webhooks

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook/github` | GitHub push HMAC |
| POST | `/webhook/github-app` | GitHub App events |
| POST | `/webhook/stripe` | Stripe billing |

### 13.6 Bootstrap (`app/main.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/metrics` | Prometheus metrics (auth in prod) |
| GET | `/docs`, `/redoc` | OpenAPI (hidden in prod if configured) |

---

## 14. Frontends

### 14.1 Next.js — primary UI (`frontend-next/`)

**URL:** http://localhost:3000  
**Stack:** Next.js 16 · React 19 · Tailwind v4 · shadcn/ui · TanStack Query · Framer Motion · mermaid · Recharts

#### Routes

| Route | File | Features |
|-------|------|----------|
| `/` | `app/page.tsx` | Redirect → `/workspace` |
| `/workspace` | `app/workspace/page.tsx` | Ingest, status stepper, chat, call graph |
| `/evaluation` | `app/evaluation/page.tsx` | RAGAS eval, golden CI, version compare |
| `/platform` | `app/platform/page.tsx` | Usage, subscription, audit log |

#### Key components

| Path | Purpose |
|------|---------|
| `components/layout/app-shell.tsx` | Page shell wrapper |
| `components/layout/header.tsx` | Top bar + API online/offline badge |
| `components/layout/sidebar.tsx` | Nav + theme toggle + quick-start repos |
| `components/layout/providers.tsx` | Theme (next-themes) + React Query |
| `components/workspace/repo-ingest-card.tsx` | Repo URL ingest form |
| `components/workspace/status-panel.tsx` | Live ingestion stepper |
| `components/workspace/chat-panel.tsx` | Chat + SSE agent steps |
| `components/workspace/chat-message.tsx` | Message bubbles + citations |
| `components/workspace/call-graph-panel.tsx` | Diagram generator |
| `components/workspace/mermaid-viewer.tsx` | Mermaid renderer |
| `components/evaluation/ragas-chart.tsx` | RAGAS metrics chart |
| `components/evaluation/per-question-diagnostics.tsx` | Per-question eval table |

#### Lib layer

| File | Purpose |
|------|---------|
| `lib/api.ts` | Typed HTTP client for all backend endpoints |
| `lib/types.ts` | TypeScript interfaces mirroring Pydantic models |
| `lib/constants.ts` | API URL, ingest steps, starter prompts, `repoIsReady()` |
| `lib/context/app-context.tsx` | Global repo ID (localStorage), per-repo chat/diagram state |
| `lib/hooks/use-backend-health.ts` | Poll `/health` |
| `lib/hooks/use-repo-status.ts` | Poll `/status/{job_id}`; stops at terminal states |
| `lib/hooks/use-eval-health.ts` | Poll `/eval/health`; invalidates when repo becomes ready |
| `lib/hooks/use-eval-history.ts` | Fetch `/eval/history` |
| `lib/hooks/use-golden-status.ts` | Fetch `/eval/golden-status` |

#### Environment (`.env.local`)

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=dev-secret-key
```

#### Commands

```bash
cd frontend-next
npm install
cp .env.local.example .env.local
npm run dev      # http://localhost:3000
npm run build    # production build
npm run lint     # ESLint
```

### 14.2 Streamlit — legacy UI (`frontend/`)

**URL:** http://localhost:8501  
**Started by:** `run_local.bat` or `streamlit run frontend/streamlit_app.py`

| File | Purpose |
|------|---------|
| `streamlit_app.py` | Main UI: ingest, status, chat, diagrams, eval, platform tabs |
| `api_client.py` | HTTP wrapper to FastAPI |
| `settings_bridge.py` | Reads `API_BASE_URL`, `API_KEY` from env |
| `ui_theme.py` | CSS, stat cards, stepper, charts |
| `theme.py` | Branding + dark/light toggle |
| `voice_input.py` / `voice_output.py` | Optional voice I/O (not ported to Next.js) |

### 14.3 Admin dashboard (`admin/`)

Vite/React admin UI with its own `api.ts` and Dockerfile. Deployed separately via `k8s/admin-deployment.yaml`.

---

## 15. Data Stores & Persistence

| Store | Default path / tech | Contents |
|-------|---------------------|----------|
| **ChromaDB** | `./data/chroma_db` or remote `CHROMA_HOST` | Per-repo chunk embeddings; semantic cache collections `sc_{repo}_{commit}` |
| **BM25** | `./bm25_index/{repo_id}/bm25.pkl` | Keyword inverted index |
| **Call graph** | `./data/graph_store/{repo_id}/graph.json` | NetworkX DiGraph JSON |
| **Repo metadata** | `./data/repos/{repo_id}/metadata.json` | Sync status, commit, progress, org_id |
| **Cloned repos** | `./data/repos/{repo_id}/clone/` | Git working tree |
| **Aliases** | `./data/repos/{job_id}/alias.json` | `job_id` → `asset_repo_id` |
| **Chat sessions** | `./data/sessions/{session_id}.json` | Last 10 conversation turns |
| **Eval results** | `eval_results/`, eval store | RAGAS run JSON artifacts |
| **Golden set** | `data/golden_set.json` | Q&A evaluation corpus |
| **Redis** | `redis://localhost:6379/0` | Celery broker, eval jobs, tool cache, webhook dedup, OAuth state |
| **PostgreSQL** | `DATABASE_URL` (optional) | Orgs, API keys, audit, usage, subscriptions |
| **HuggingFace cache** | `./data/huggingface` (Docker) | Embedding + reranker model weights |

---

## 16. Configuration & Environment

All settings are defined in `app/config.py` (Pydantic `BaseSettings`). Template: `.env.example`.

### Critical variables

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq LLM API key |
| `LLM_PROVIDER` | `groq` or `ollama` |
| `LLM_MODEL` | Model name (e.g. llama-3.x) |
| `API_KEY` | Dev API key (`dev-secret-key`) |
| `DATA_PATH` | Root for repos, sessions, etc. |
| `CHROMA_DB_PATH` | Local Chroma path |
| `BM25_INDEX_PATH` | BM25 pickle directory |
| `GRAPH_STORE_PATH` | Graph JSON directory |
| `REPOS_PATH` | Cloned repos parent |
| `REDIS_URL` | Redis connection (optional) |
| `DATABASE_URL` | PostgreSQL (optional; JSON fallback) |
| `MAX_AGENT_ITERATIONS` | Agent loop cap |
| `CACHE_SIMILARITY_THRESHOLD` | Semantic cache threshold (~0.95) |
| `CONFIDENCE_GATE_THRESHOLD` | Gating threshold (default 4.0) |
| `STRIPE_SECRET_KEY` | Stripe billing |
| `OIDC_*` / `SAML_*` | SSO configuration |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC verification |

---

## 17. How to Run Locally

### Prerequisites

- Python 3.12
- Node.js 20+ (for Next.js)
- Git
- Optional: Redis (Celery), PostgreSQL (platform persistence)

### Option A — Windows quick start (Streamlit)

```bat
run_local.bat
```

| Service | URL |
|---------|-----|
| FastAPI | http://localhost:8000 |
| Streamlit | http://localhost:8501 |
| API docs | http://localhost:8000/docs |

### Option B — Full stack with Next.js (recommended)

**Terminal 1 — Backend:**

```bash
cd codebase-onboarding-agent
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # edit GROQ_API_KEY, API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — Next.js:**

```bash
cd frontend-next
cp .env.local.example .env.local
npm install
npm run dev
```

Open http://localhost:3000/workspace

### Option C — Docker Compose

```bash
docker-compose up
```

Services: chromadb, redis, backend, celery worker, streamlit.

### Option D — Celery worker (async ingestion)

```bash
celery -A app.tasks.celery_app worker -l info -Q ingestion --pool=solo
```

---

## 18. Testing

### Pytest suite

```bash
pytest tests/                  # full suite (~551 tests)
pytest tests/test_module_12.py -v   # single module
pytest tests/ --cov=app --cov-report=html
```

**Location:** `tests/` (~70 modules)  
**Fixtures:** `conftest.py` — mocks Redis/Celery, bypasses quotas, resets agent globals  
**Live tests:** `test_golden_set.py` — real API calls, skipped by default

### Frontend QA

```bash
python scratch/qa_frontend_sweep.py    # API + SSR route sweep
python scratch/verify_next_api.py      # 7-point API smoke test
```

### Eval CLI

```bash
python eval/run_eval.py
python eval/compare_runs.py
```

---

## 19. Scripts & Diagnostics

### `scripts/` (operational)

| Script | Purpose |
|--------|---------|
| `audit_ingestion_pipeline.py` | Systematic ingestion pipeline audit |
| `diag_status_vs_eval.py` | Compare `/status` vs eval readiness signals |
| `collect_p0_evidence.py` | P0 false-block evidence for chat readiness |
| `diagnose_groq_latency.py` | Groq latency diagnostics |
| `diagnose_verify_full_loop.py` | Full agent VERIFY loop diagnosis |
| `live_chat_check.py` | Live `/chat` latency smoke test |
| `retrieval_ablation.py` | Retrieval-only ablation vs golden set |
| `verify_regression_chat.py` | Chat regression verification |
| `eval_per_question_report.py` | Per-question eval report generator |

### `scratch/` (ad-hoc verification)

| Script | Purpose |
|--------|---------|
| `qa_frontend_sweep.py` | Full frontend QA sweep (29 test cases) |
| `verify_next_api.py` | Next.js API layer smoke test |
| `poll_eval_job.py` | Poll eval job until done |
| `test_e2e_chat_diagram.py` | E2E chat + diagram test |
| `test_e2e_ingestion.py` | E2E ingestion test |
| `diag_eval_readiness.py` | Eval readiness diagnostics |

---

## 20. Deployment & CI/CD

### Docker

- `Dockerfile` — backend image
- `frontend/Dockerfile` — Streamlit image
- `frontend-next/` — build with `npm run build` + `npm start`
- `docker-compose.yml` — local full stack
- `docker-compose.prod.yml` — production overrides

### Kubernetes (`k8s/`)

Manifests for: backend, celery worker, chromadb, redis, ingress, HPA, admin dashboard.

### GitHub Actions (`.github/workflows/`)

| Workflow | Purpose |
|----------|---------|
| `ci.yml` | Pytest on push/PR |
| `eval.yml` | Golden-set CI pipeline |

---

## 21. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Triple index** (vector + BM25 + graph) | Semantic search misses exact symbols; BM25 misses concepts; graph answers "who calls whom" |
| **AST-level chunking** | Never split mid-function — preserves logical context for RAG |
| **Agentic loop vs fixed pipeline** | LLM chooses tools dynamically based on question type |
| **Deterministic confidence gating** | LLM self-assessment is unreliable; citation validation is not |
| **job_id ↔ asset_repo_id aliases** | Same repo URL always maps to same asset; job_id is per-ingest request |
| **`repo_readiness.py` as single source** | Prevents `/status` and `/eval/health` disagreeing on readiness |
| **Semantic cache commit-scoped** | Answers invalidated automatically when webhook re-ingests new commit |
| **JSON metadata store vs shelve** | Human-readable, atomic writes, cross-platform |
| **Next.js alongside Streamlit** | Modern UX without breaking existing Streamlit users |
| **Groq for LLM** | Fast inference; local embeddings/reranker avoid API cost on retrieval |

---

## 22. Related Documentation Files

| File | Contents |
|------|----------|
| `README.md` | Marketing README, quick start, feature highlights |
| `PROJECT_OVERVIEW.md` | Shorter architecture guide with Mermaid diagram |
| `PROJECT_BLUEPRINT.md` | Build blueprint and module ordering |
| `MODULES.md` | Incremental module build-order reference |
| `BUILD_LOG.md` | Development build log |
| `SECURITY.md` | Vulnerability reporting |
| `CONTRIBUTING.md` | Contribution guidelines |
| `docs/` | Deployment, legal, commercial documentation |
| `frontend-next/README.md` | Next.js frontend setup |

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│  START BACKEND:  uvicorn app.main:app --port 8000           │
│  START NEXT UI:  cd frontend-next && npm run dev            │
│  START STREAMLIT: streamlit run frontend/streamlit_app.py   │
│  RUN TESTS:      pytest tests/                              │
│  RUN EVAL:       python eval/run_eval.py                    │
│  API KEY HEADER: X-API-Key: dev-secret-key                  │
│  INGEST:         POST /ingest { repo_url, ref }             │
│  CHAT:           POST /chat { repo_id, question }           │
│  DIAGRAM:        GET /diagram/{repo_id}/{symbol}?depth=2    │
│  EVAL HEALTH:    GET /eval/health/{repo_id}                 │
└─────────────────────────────────────────────────────────────┘
```

---

*Last updated: July 2026 — reflects Next.js frontend migration, `repo_readiness` unification, and full QA sweep.*
