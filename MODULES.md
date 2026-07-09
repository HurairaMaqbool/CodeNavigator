# MODULES.md — Codebase Onboarding Agent

> **Purpose of this file:** This is the single source of truth for every backend module — its purpose, its exact upstream/downstream links, its functions, its internal workflow, its data contracts, and its error handling.
>
> **How to use this file with an AI coding agent:** Before asking the AI to write or edit any module, paste (or point it to) this file plus `PROJECT_BLUEPRINT.md`. Always tell the AI *which module path* you are working on. The AI should never invent a function signature, input/output shape, or dependency that contradicts what is written here — this file is the contract.

---

## Build Order (do not skip ahead)

Modules must be implemented top-to-bottom. Every module's dependencies are guaranteed to already exist by the time you reach it.

1. `app/config.py` — Layer 1 — Configuration & Bootstrap
2. `app/main.py` — Layer 1 — Configuration & Bootstrap
3. `app/api/router.py` — Layer 2 — API Layer
4. `app/api/auth.py` — Layer 2 — API Layer
5. `app/api/rate_limiter.py` — Layer 2 — API Layer
6. `app/ingestion/locking.py` — Layer 3 — Ingestion Pipeline
7. `app/ingestion/clone.py` — Layer 3 — Ingestion Pipeline
8. `app/ingestion/file_filter.py` — Layer 3 — Ingestion Pipeline
9. `app/ingestion/metadata_store.py` — Layer 3 — Ingestion Pipeline
10. `app/parsing/tree_sitter_parser.py` — Layer 4 — Parsing & Chunking
11. `app/parsing/chunker.py` — Layer 4 — Parsing & Chunking
12. `app/retrieval/embeddings.py` — Layer 5 — Retrieval & Storage
13. `app/retrieval/vector_store.py` — Layer 5 — Retrieval & Storage
14. `app/retrieval/bm25_store.py` — Layer 5 — Retrieval & Storage
15. `app/retrieval/hybrid_search.py` — Layer 5 — Retrieval & Storage
16. `app/retrieval/reranker.py` — Layer 5 — Retrieval & Storage
17. `app/retrieval/query_expansion.py` — Layer 5 — Retrieval & Storage
18. `app/graph/builder.py` — Layer 6 — Graph Operations
19. `app/graph/queries.py` — Layer 6 — Graph Operations
20. `app/diagrams/mermaid_generator.py` — Layer 6 — Graph Operations
21. `app/agent/loop.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
22. `app/agent/tools.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
23. `app/agent/prompts/ (plan_prompt.py, decide_prompt.py, finalize_prompt.py, compress_prompt.py)` — Layer 7 — Agentic Loop Engine (State-Machine Design)
24. `app/agent/semantic_cache.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
25. `app/agent/context_manager.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
26. `app/agent/confidence.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
27. `app/agent/onboarding_path.py` — Layer 7 — Agentic Loop Engine (State-Machine Design)
28. `eval/run_eval.py` — Layer 8 — Evaluation Suite
29. `eval/compare_runs.py` — Layer 8 — Evaluation Suite
30. `app/api/state_stream.py` — Layer 9 — Frontend & Voice UX (New)
31. `frontend/loading_experience.py` — Layer 9 — Frontend & Voice UX (New)
32. `frontend/voice_input.py` — Layer 9 — Frontend & Voice UX (New)
33. `frontend/voice_output.py` — Layer 9 — Frontend & Voice UX (New)
34. `frontend/theme.py` — Layer 9 — Frontend & Voice UX (New)

---

## Layer 1 — Configuration & Bootstrap

### 1. `app/config.py`

**Role:** Single source of truth for all environment variables and runtime settings.

**Purpose**

Defines a Pydantic BaseSettings class that reads every environment variable exactly once at process start. No other module is allowed to call os.environ directly — this prevents configuration drift and makes the whole system testable by injecting a fake settings object.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Loaded first by app/main.py during application bootstrap, before any router or agent module is imported.
- Reads values from .env (GROQ_API_KEY, LLM_PROVIDER, API_KEY, WEBHOOK_SECRET, MIN_CONFIDENCE_SCORE, MAX_ITERATIONS).

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Every module in Layers 2–7 imports the shared `settings` object from here (api/auth.py, agent/loop.py, retrieval/embeddings.py, etc.).
- app/agent/loop.py reads MAX_ITERATIONS and MIN_CONFIDENCE_SCORE from settings — these are never hardcoded inside the loop.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `class Settings(BaseSettings)` | env vars | typed settings object | Declares every config field with a type and default; Pydantic validates on load and fails fast if a required key is missing. |
| `get_settings()` | none (cached) | Settings instance | lru_cache-wrapped accessor so the object is constructed once per process, not per request. |

**Internal Workflow (pipeline steps inside this module)**

1. Process starts → Settings() is instantiated once.
2. Pydantic validates types (e.g. MIN_CONFIDENCE_SCORE must be float 0–10).
3. If a required variable is missing, the process exits immediately with a clear error instead of failing later inside a request.
4. get_settings() is imported everywhere else via dependency injection.

**Data Contract**

- **Input:** .env file / OS environment variables (strings).
- **Output:** Settings object with typed, validated fields (str, int, float, bool).

**Error Handling & Edge Cases**

- Missing required key → raise a startup-time ValidationError, never a runtime 500.
- Invalid type (e.g. MAX_ITERATIONS='abc') → fail at boot, not mid-request.

> **Cost / Design Note:** Because Groq is the only paid-adjacent dependency, GROQ_API_KEY and LLM_PROVIDER live here so switching providers later never requires touching business logic.

---

### 2. `app/main.py`

**Role:** FastAPI application bootstrap and dependency wiring.

**Purpose**

Creates the FastAPI app instance, registers middleware (CORS, logging), attaches global exception handlers, and mounts the router from app/api/router.py. This is the only file that is executed directly (uvicorn app.main:app).

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Imports `settings` from app/config.py first — nothing else may be imported before configuration is loaded and validated.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Mounts app/api/router.py, which then wires in auth.py, rate_limiter.py, and the agent loop.
- Registers a startup event that warms the embeddings model (app/retrieval/embeddings.py) and the reranker so the first real request is not slowed down by a cold model load.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `create_app()` | Settings | FastAPI instance | Factory function so tests can build isolated app instances with mock settings. |
| `on_startup()` | none | none (side effects) | Preloads embedding model + Cross-Encoder reranker into memory once. |
| `global_exception_handler(request, exc)` | Request, Exception | JSON error response | Ensures unhandled exceptions never leak stack traces to the client; logs full trace server-side. |

**Internal Workflow (pipeline steps inside this module)**

1. Import settings (Layer 1) → validate.
2. Instantiate FastAPI app.
3. Register middleware (CORS, request-ID logging).
4. Mount router from app/api/router.py.
5. Run on_startup(): warm embeddings + reranker models.
6. Serve.

**Data Contract**

- **Input:** None directly — this is the process entry point.
- **Output:** A running ASGI application object.

**Error Handling & Edge Cases**

- Any startup failure (bad config, model download failure) stops the process before it accepts traffic — never a silently half-broken server.

> **Cost / Design Note:** Free-tier note: model warm-up (embeddings/reranker) happens locally via HuggingFace, so this step costs compute time only, never a Groq call.

---

## Layer 2 — API Layer

### 3. `app/api/router.py`

**Role:** REST endpoint definitions and request orchestration.

**Purpose**

Exposes /ingest, /status/{repo_id}, /chat, /diagram, and the new /onboarding-path endpoint. Every endpoint is a thin controller: it validates the request shape, checks auth, then delegates to the correct pipeline (ingestion state machine or agent state machine) — it contains no business logic itself.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Mounted by app/main.py.
- Every request first passes through app/api/auth.py (X-API-Key check) and app/api/rate_limiter.py before reaching a route handler.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- /ingest → app/ingestion/clone.py (Layer 3 state machine).
- /chat → app/agent/loop.py (Layer 7 state machine).
- /diagram → app/graph/queries.py + app/diagrams/mermaid_generator.py.
- /onboarding-path (NEW) → app/agent/onboarding_path.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `POST /ingest` | {repo_url, ref, force_reindex} | 202 {job_id, status} | Validates URL, checks app/ingestion/locking.py, schedules a background task. |
| `GET /status/{repo_id}` | path param | {sync_status, commit_hash, error} | Reads app/ingestion/metadata_store.py directly, no LLM involved. |
| `POST /chat` | {repo_id, question, session_id} | {answer, sources, confidence_score, gated} | Invokes the Layer 7 state machine end to end. |
| `POST /diagram` | {repo_id, entry_point, direction} | {mermaid_markdown} | Calls graph queries then the mermaid generator; zero LLM cost. |
| `POST /onboarding-path` | {repo_id, role, experience_level} | ordered file list | Calls the onboarding path generator (Layer 7). |

**Internal Workflow (pipeline steps inside this module)**

1. Request arrives → auth.py validates X-API-Key.
2. rate_limiter.py checks sliding-window quota for this key.
3. Router validates request body against a Pydantic schema (reject malformed input with 422 before any downstream module runs).
4. Router delegates to the correct pipeline module and awaits its result.
5. Router serializes the pipeline's output into the documented response contract and returns it.

**Data Contract**

- **Input:** JSON bodies per endpoint, documented above; all requests require header X-API-Key.
- **Output:** JSON responses per endpoint; errors follow a single {error_code, message} shape from main.py's global handler.

**Error Handling & Edge Cases**

- Malformed JSON / missing fields → 422 before touching ingestion or agent modules.
- Unknown repo_id on /chat or /diagram → 404 with a clear message, not a silent empty answer.
- Downstream state-machine failure → 500 with a logged trace ID, never a partial/garbled JSON body.

> **Cost / Design Note:** This module intentionally has zero direct LLM calls — it is pure routing, which keeps it 100% free and instantly testable.

---

### 4. `app/api/auth.py`

**Role:** Request authentication gate.

**Purpose**

Validates the X-API-Key header against settings.API_KEY (or a per-tenant key store, once multi-tenant billing exists) before any route handler runs.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Reads settings.API_KEY from app/config.py.
- Invoked as a FastAPI dependency on every route in app/api/router.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Blocks all Layer 3–7 modules from ever executing on an unauthenticated request.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `verify_api_key(x_api_key: str = Header(...))` | header value | raises HTTPException(401) or passes | Constant-time string comparison to avoid timing attacks. |

**Internal Workflow (pipeline steps inside this module)**

1. Extract X-API-Key header.
2. Compare against known key(s) using constant-time comparison.
3. Pass request through on match; raise 401 immediately on mismatch, before any DB/model access.

**Data Contract**

- **Input:** HTTP header X-API-Key: <string>.
- **Output:** None on success (request proceeds); HTTP 401 JSON error on failure.

**Error Handling & Edge Cases**

- Missing header → 401.
- Invalid key → 401 (same generic message for both, to avoid leaking which case failed).

> **Cost / Design Note:** Zero cost, zero external dependency — pure in-memory comparison.

---

### 5. `app/api/rate_limiter.py`

**Role:** Sliding-window request throttling.

**Purpose**

Protects the free-tier Groq quota and the server itself from being exhausted by a single client. Implemented as an in-memory sliding-window counter keyed by API key.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Runs immediately after auth.py succeeds, before the route handler body executes.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Prevents excess load from ever reaching app/agent/loop.py, which is the only module that spends Groq tokens.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `check_rate_limit(api_key, endpoint)` | key, endpoint name | raises HTTPException(429) or passes | Maintains a per-key deque of timestamps; evicts entries outside the window on each call. |

**Internal Workflow (pipeline steps inside this module)**

1. On each request, look up the key's timestamp deque.
2. Drop timestamps older than the configured window.
3. If remaining count >= limit, reject with 429 and a Retry-After header.
4. Otherwise append the current timestamp and allow the request through.

**Data Contract**

- **Input:** API key (string) + endpoint name.
- **Output:** Pass-through on success; HTTP 429 with Retry-After on limit breach.

**Error Handling & Edge Cases**

- Limit breached → 429, never a silent queue or hang.

> **Cost / Design Note:** Keep the /chat limit intentionally tight while on Groq's free tier; raise it only once paid usage funds a higher tier.

---

## Layer 3 — Ingestion Pipeline

### 6. `app/ingestion/locking.py`

**Role:** Per-repository mutual exclusion.

**Purpose**

Ensures two ingestion jobs (or an ingestion job and a webhook re-sync) never run against the same repo_id concurrently, which would corrupt the vector store, BM25 index, or graph mid-write.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Called first by app/api/router.py's /ingest handler and by the webhook handler, before clone.py starts.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Guards writes made by clone.py, file_filter.py, tree_sitter_parser.py, chunker.py, and metadata_store.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `acquire_lock(repo_id)` | repo_id | bool (acquired or not) | Thread-level lock keyed by repo_id; non-blocking check with a short wait. |
| `release_lock(repo_id)` | repo_id | none | Always called in a finally block so a crash mid-ingestion cannot leave a permanent deadlock. |

**Internal Workflow (pipeline steps inside this module)**

1. Ingestion or webhook handler requests a lock for repo_id.
2. If already locked, the request returns immediately with sync_status='syncing' instead of queuing indefinitely.
3. If acquired, the full ingestion state machine (Layer 3) runs to completion.
4. Lock is released in a finally block regardless of success or failure.

**Data Contract**

- **Input:** repo_id (string).
- **Output:** Boolean lock state; no persistent storage beyond process memory.

**Error Handling & Edge Cases**

- Lock already held → caller gets a clear 'currently syncing' response, not a hang or silent overwrite.

> **Cost / Design Note:** In-memory locking is sufficient for a single-process deployment; if scaled to multiple workers later, this upgrades to a Redis-backed lock with the same interface.

---

### 7. `app/ingestion/clone.py`

**Role:** Repository acquisition (state: PENDING → CLONING).

**Purpose**

Clones or fetches the target repository at the requested ref. Falls back to a bundled dummy repository if the network is unavailable, so local demos never crash.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Runs after locking.py has granted the lock.
- Reads repo_url/ref from the validated /ingest request body.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Hands the local repo path to app/ingestion/file_filter.py.
- Writes a CLONING → CLONED checkpoint to metadata_store.py before handing off.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `clone_repo(repo_url, ref)` | url, ref | local filesystem path | Shallow clone (depth=1) for speed; verifies repo size against a configured max before proceeding. |
| `fallback_dummy_repo()` | none | local path | Used only if clone_repo fails due to network/DNS errors. |

**Internal Workflow (pipeline steps inside this module)**

1. Check repo size/visibility (skip private repos unless explicitly permitted).
2. Attempt shallow git clone at the given ref.
3. On failure, log the reason and use the bundled dummy repo so downstream stages still have valid input for local testing.
4. Write checkpoint CLONED with the resolved commit hash to metadata_store.py.

**Data Contract**

- **Input:** {repo_url: str, ref: str}.
- **Output:** Local filesystem path + resolved commit_hash.

**Error Handling & Edge Cases**

- Oversized repo → reject before cloning (protects disk and downstream token usage).
- Network failure → fallback path, never an unhandled exception bubbling to the API layer.

> **Cost / Design Note:** No LLM involved — this stage is pure I/O and costs nothing beyond local disk/CPU.

---

### 8. `app/ingestion/file_filter.py`

**Role:** Source-file selection (state: CLONED → FILTERING).

**Purpose**

Walks the cloned repo and keeps only supported, non-binary source files (Python, JS, TS, and — per the advanced roadmap — Go, Java, Rust), dropping binaries, images, and minified bundles before any expensive parsing happens.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives the local repo path and commit_hash from clone.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Passes the clean file list to app/parsing/tree_sitter_parser.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `filter_repo_files(repo_path)` | path | list[str] of file paths | Applies an extension allowlist and a byte-size ceiling; skips node_modules/vendor/dist-style directories. |
| `is_minified(file_path)` | path | bool | Heuristic check (average line length) to drop minified JS bundles that would waste chunking/embedding effort. |

**Internal Workflow (pipeline steps inside this module)**

1. List all files under the repo root.
2. Drop anything outside the extension allowlist.
3. Drop anything above the size ceiling or flagged as minified.
4. Return the clean list; write a FILTERED checkpoint with the file count to metadata_store.py.

**Data Contract**

- **Input:** Local repo path (string).
- **Output:** List of relative file paths considered safe and useful to parse.

**Error Handling & Edge Cases**

- Zero files remain after filtering → mark ingestion FAILED with a descriptive reason, instead of proceeding on an empty index.

> **Cost / Design Note:** Free and CPU-only; the size/extension checks are also what keep the free-tier token budget under control later at embedding time.

---

### 9. `app/ingestion/metadata_store.py`

**Role:** Per-repository state and checkpoint persistence.

**Purpose**

The single durable record of each repository's ingestion state (PENDING, CLONING, FILTERING, PARSING, INDEXING, SYNCED, FAILED), its current commit hash, and its last successful checkpoint — enabling the resumable ingestion state machine described in the Advanced Architecture Blueprint.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Written to by every stage of the ingestion pipeline (clone.py, file_filter.py, tree_sitter_parser.py, chunker.py, the indexing stage).

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Read by GET /status/{repo_id}.
- Read by app/agent/loop.py's INTAKE state to confirm the repo is SYNCED before answering a question.
- Read by the webhook handler's reconciliation check (Section 8 of the Advanced Blueprint) to detect missed webhook events.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `update(repo_id, stage, commit_hash=None, error=None)` | repo_id, stage enum | none | Idempotent checkpoint write; safe to call repeatedly for the same stage. |
| `get(repo_id)` | repo_id | {sync_status, commit_hash, error, has_circular_dependencies} | Read path used by /status and by the agent loop. |
| `last_checkpoint(repo_id)` | repo_id | stage enum | Used on retry to resume ingestion at the correct stage instead of restarting. |

**Internal Workflow (pipeline steps inside this module)**

1. Each ingestion stage calls update() on success before handing off to the next stage.
2. On failure, update() records stage=FAILED plus the error reason; the stage itself is NOT marked complete.
3. On retry, last_checkpoint() tells the pipeline which stage to resume from.

**Data Contract**

- **Input:** repo_id (string) + stage transitions.
- **Output:** A durable per-repo record, persisted to disk (shelve-backed dictionary).

**Error Handling & Edge Cases**

- Concurrent writes to the same repo_id are prevented upstream by locking.py, so this module can assume single-writer access.

> **Cost / Design Note:** This module is what makes the ingestion pipeline resumable and is a prerequisite for the Section-5 'Ingestion Pipeline v2' resumability feature.

---

## Layer 4 — Parsing & Chunking

### 10. `app/parsing/tree_sitter_parser.py`

**Role:** AST extraction (state: FILTERED → PARSING).

**Purpose**

Uses Tree-sitter grammars to parse each filtered file into an Abstract Syntax Tree, extracting class definitions, function definitions, and import statements with byte-accurate line ranges. The advanced roadmap adds Go, Java, and Rust grammars alongside the existing Python/JS/TS support.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives the clean file list from app/ingestion/file_filter.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Passes structured AST nodes (with exact line ranges) to app/parsing/chunker.py.
- Import/call statements extracted here are also the raw input to app/graph/builder.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `parse_file(file_path, language)` | path, language enum | AST node tree | Selects the correct Tree-sitter grammar by file extension. |
| `extract_definitions(ast)` | AST | list of {name, type, start_line, end_line} | Walks the tree collecting function/class/import nodes; this is the exact source of truth confidence.py later checks citations against. |

**Internal Workflow (pipeline steps inside this module)**

1. For each file, detect language from extension and load the matching grammar.
2. Parse to an AST.
3. Extract function/class/import nodes with precise start/end line numbers.
4. Emit structured definitions; write a PARSING-progress checkpoint (files processed / total) to metadata_store.py so a crash mid-parse can resume.

**Data Contract**

- **Input:** List of file paths + detected language.
- **Output:** Per-file list of {name, type, start_line, end_line, raw_text}.

**Error Handling & Edge Cases**

- Unparseable file (syntax error in source) → skip that file, log a warning, continue the batch — one bad file must never fail the whole ingestion.
- Unsupported language reaching this stage → should be impossible because file_filter.py already restricts extensions; if it happens, treat as a filter-layer bug and fail loudly in tests.

> **Cost / Design Note:** Tree-sitter grammars are free and open-source; adding Go/Java/Rust support costs zero external spend, only development time.

---

### 11. `app/parsing/chunker.py`

**Role:** LLM-digestible chunk creation.

**Purpose**

Splits each file's AST-derived definitions into chunks along logical function/class boundaries, never mid-statement, so retrieved context always reads as complete, coherent code.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives structured AST definitions from tree_sitter_parser.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Chunks go to app/retrieval/embeddings.py (for vector storage) and app/retrieval/bm25_store.py (for lexical indexing) simultaneously.
- Each chunk's {file_path, function_name, start_line, end_line} is preserved end-to-end — this is exactly the tuple app/agent/confidence.py validates citations against later.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `chunk_definitions(definitions, max_tokens)` | definitions list, token budget | list of Chunk objects | Groups small adjacent functions together up to max_tokens; splits very large single functions into overlapping sub-chunks only as a last resort, always at a statement boundary. |

**Internal Workflow (pipeline steps inside this module)**

1. Iterate definitions in file order.
2. Merge small consecutive definitions into one chunk until the token budget is reached.
3. If a single definition exceeds the budget, split at the nearest statement boundary rather than mid-line.
4. Attach exact metadata (file_path, function_name, start_line, end_line) to every chunk.

**Data Contract**

- **Input:** Per-file structured definitions from tree_sitter_parser.py.
- **Output:** List of Chunk{text, file_path, function_name, start_line, end_line}.

**Error Handling & Edge Cases**

- A definition with zero extractable text (e.g. empty stub) → still chunked with a minimal placeholder so line-range citations remain valid even for trivial functions.

> **Cost / Design Note:** Correct chunk boundaries are what make the Hallucination Guard's line-range check (Section 9 of the Blueprint) meaningful — sloppy chunking here directly weakens Layer 7 verification.

---

## Layer 5 — Retrieval & Storage

### 12. `app/retrieval/embeddings.py`

**Role:** Text-to-vector conversion.

**Purpose**

Wraps a local sentence-transformers model to convert chunk text (and incoming questions) into embeddings, entirely on CPU, with zero Groq/API cost.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Warmed once at startup by app/main.py.
- Receives chunk text from chunker.py during ingestion, and question text from the agent loop's PLAN state during chat.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Embeddings are written to app/retrieval/vector_store.py (ChromaDB) during ingestion, and passed live to hybrid_search.py during chat.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `embed_texts(texts: list[str])` | list of strings | list of vectors | Batches texts for throughput; model stays resident in memory after startup warm-up. |

**Internal Workflow (pipeline steps inside this module)**

1. Ingestion: batch-embed all chunks from a repo, write to vector_store.py.
2. Chat: embed the single incoming question inside the PLAN/ACT states so search_code can query ChromaDB.

**Data Contract**

- **Input:** list[str] of raw text (chunks or questions).
- **Output:** list[list[float]] embedding vectors, dimension fixed by the loaded model.

**Error Handling & Edge Cases**

- Empty string input → return a zero-vector placeholder rather than raising, so a single malformed chunk cannot abort a whole ingestion batch.

> **Cost / Design Note:** 100% free — runs locally via HuggingFace sentence-transformers, no external API call, no per-token cost.

---

### 13. `app/retrieval/vector_store.py`

**Role:** Semantic index (ChromaDB interface).

**Purpose**

Persists chunk embeddings with their metadata (file_path, function_name, start_line, end_line, repo_id, commit_hash) and exposes similarity search filtered by repo_id and commit_hash.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives embeddings from embeddings.py and chunk metadata from chunker.py during ingestion.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Queried by app/retrieval/hybrid_search.py during the ACT state of the agent loop.
- Also queried directly by app/agent/semantic_cache.py to find similar past questions.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `upsert_chunks(repo_id, commit_hash, chunks, vectors)` | repo/commit + chunk batch | none | Writes/overwrites the collection scoped to this repo+commit. |
| `query(repo_id, commit_hash, query_vector, k)` | scoped query + top-k | list of {chunk, score} | Always filters by repo_id AND commit_hash so a stale index from a previous commit can never leak into a fresh answer. |

**Internal Workflow (pipeline steps inside this module)**

1. Ingestion writes a fresh collection per (repo_id, commit_hash).
2. Chat-time queries always pass the current commit_hash from metadata_store.py, guaranteeing answers reflect the latest synced code.

**Data Contract**

- **Input:** Vectors + metadata dict per chunk.
- **Output:** Ranked list of {chunk_metadata, similarity_score}.

**Error Handling & Edge Cases**

- Query against a repo_id with no synced collection → return an empty result with a clear 'not yet indexed' signal, not an exception.

> **Cost / Design Note:** Local, free, disk-backed. Old commit collections are purged by the webhook cache-purge workflow described in Layer 7.

---

### 14. `app/retrieval/bm25_store.py`

**Role:** Lexical/exact-match index.

**Purpose**

A pure-Python BM25 implementation over tokenized code chunks, catching exact variable/function-name matches that semantic embeddings can miss (e.g. searching for a specific error-code string).

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives the same chunk batch as vector_store.py, from chunker.py during ingestion.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Queried by hybrid_search.py in parallel with vector_store.py; results are fused via Reciprocal Rank Fusion.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `index_chunks(repo_id, commit_hash, chunks)` | repo/commit + chunks | none | Tokenizes code-aware (splits on camelCase/snake_case boundaries) and builds the BM25 corpus. |
| `search(repo_id, commit_hash, query_text, k)` | scoped query | list of {chunk, score} | Exact/keyword-weighted ranking, complementary to the semantic vector search. |

**Internal Workflow (pipeline steps inside this module)**

1. Ingestion tokenizes and indexes every chunk alongside the vector store write (parallel step, not sequential).
2. Chat time: same query text used for embeddings is also passed here unmodified.

**Data Contract**

- **Input:** Chunk batch with raw text.
- **Output:** Ranked list of {chunk_metadata, bm25_score}.

**Error Handling & Edge Cases**

- Query with zero token overlap → empty result set is valid and expected; hybrid_search.py handles the empty-branch case.

> **Cost / Design Note:** Pure Python, zero external dependency, zero cost, and disk-persisted as a pickle per repo+commit.

---

### 15. `app/retrieval/hybrid_search.py`

**Role:** Result fusion.

**Purpose**

Combines vector_store.py and bm25_store.py results using Reciprocal Rank Fusion (RRF) — a deterministic, LLM-free ranking merge — before handing the top candidates to the reranker.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Called from within the agent loop's ACT state whenever the search_code tool is invoked.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Passes its fused top-N list to app/retrieval/reranker.py for final re-ordering.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `fuse(vector_results, bm25_results, k)` | two ranked lists | single ranked list | RRF formula: score = sum(1 / (rank + constant)) across both lists; pure arithmetic, no model call. |

**Internal Workflow (pipeline steps inside this module)**

1. Run vector_store.query() and bm25_store.search() in parallel.
2. Apply RRF to merge the two rank orders into one.
3. Truncate to the configured top-N before handing off to the reranker (keeps the Cross-Encoder's per-call cost bounded).

**Data Contract**

- **Input:** Two ranked lists of {chunk_metadata, score}.
- **Output:** Single fused ranked list, length ≤ top-N.

**Error Handling & Edge Cases**

- One of the two input lists is empty → fusion degrades gracefully to ranking by the other list alone.

> **Cost / Design Note:** Zero LLM cost — this entire fusion step is arithmetic and runs in milliseconds.

---

### 16. `app/retrieval/reranker.py`

**Role:** Precision re-ordering.

**Purpose**

Runs a local Cross-Encoder model over the fused top-N candidates to re-score true relevance to the question, since RRF alone is a rank heuristic, not a relevance model.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives the fused list from hybrid_search.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Passes the final re-ordered, trimmed list to app/agent/loop.py's OBSERVE state as the search_code tool's result.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `rerank(question, candidates, top_k)` | question text, candidate chunks | re-ordered list, length top_k | Cross-Encoder scores (question, chunk) pairs jointly, which is more accurate than independent embedding similarity. |

**Internal Workflow (pipeline steps inside this module)**

1. Receive up to top-N candidates from hybrid_search.py.
2. Score each (question, chunk) pair with the local Cross-Encoder.
3. Sort descending and truncate to top_k before returning to the agent loop.

**Data Contract**

- **Input:** Question text + candidate chunk list.
- **Output:** Re-ordered, truncated chunk list with relevance scores.

**Error Handling & Edge Cases**

- Candidate list empty → return empty immediately, skip the model call entirely (saves CPU).

> **Cost / Design Note:** Runs locally via a small HuggingFace Cross-Encoder — CPU cost only, never routed through Groq, keeping this stage free regardless of query volume.

---

### 17. `app/retrieval/query_expansion.py`

**Role:** Optional query enrichment.

**Purpose**

Asks the LLM to generate likely synonyms or code keywords for a natural-language question before it hits the search index (e.g. 'login' → also try 'authenticate', 'session', 'signin').

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Invoked optionally from the agent loop's PLAN state, only when the DECIDE state determines the first search attempt returned weak results.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Its expanded keyword set is passed back into hybrid_search.py as additional query variants.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `expand_query(question)` | question text | list of keyword variants | Single, narrow-purpose Groq call constrained to return a short JSON list, not free text. |

**Internal Workflow (pipeline steps inside this module)**

1. Only triggered when initial search confidence is low (few/no strong hits).
2. Ask the LLM (Groq) for a small set of synonyms/keywords.
3. Re-run hybrid_search.py with the expanded terms.

**Data Contract**

- **Input:** Question text (string).
- **Output:** list[str] of 3–6 keyword variants.

**Error Handling & Edge Cases**

- LLM returns malformed JSON → fall back to the original question only, never block the loop waiting for a clean response.

> **Cost / Design Note:** This is a deliberately optional, gated LLM call — it only fires on weak search results, keeping average Groq usage low per the zero-cost operating rules.

---

## Layer 6 — Graph Operations

### 18. `app/graph/builder.py`

**Role:** Call-graph construction (state: INDEXING).

**Purpose**

Analyzes import statements and internal function calls extracted by tree_sitter_parser.py to build a NetworkX directed graph of the codebase, where nodes are functions/classes and edges are call/import relationships.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives import/call data from tree_sitter_parser.py, run in parallel with the vector/BM25 indexing steps.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- The resulting graph is queried by app/graph/queries.py (get_callers/get_callees).
- Also used directly by app/agent/onboarding_path.py to find architecturally central files.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `build_graph(repo_id, commit_hash, definitions)` | parsed definitions | networkx.DiGraph | Adds one node per function/class; adds a directed edge for every detected call or import. |
| `detect_circular_dependencies(graph)` | graph | bool + cycle list | Feeds the has_circular_dependencies flag returned by GET /status/{repo_id}. |

**Internal Workflow (pipeline steps inside this module)**

1. Build nodes from all extracted definitions.
2. Add edges from detected call/import relationships.
3. Run cycle detection once and cache the result in metadata_store.py.
4. Persist the graph (pickled per repo_id+commit_hash) for fast reload on later queries.

**Data Contract**

- **Input:** Structured definitions with call/import metadata.
- **Output:** networkx.DiGraph, persisted to disk per (repo_id, commit_hash).

**Error Handling & Edge Cases**

- Call target cannot be resolved (e.g. dynamic dispatch) → skip that edge rather than guessing, to avoid polluting the graph with false relationships.

> **Cost / Design Note:** Zero LLM cost — pure graph construction, and it directly powers two free (non-LLM) query capabilities in Layer 7: get_callers/get_callees and onboarding path ranking.

---

### 19. `app/graph/queries.py`

**Role:** Structural lookup tools.

**Purpose**

Provides timeout-safe, depth-limited (3-hop max) traversal over the persisted call graph so the agent can answer 'who calls this?' / 'what does this call?' without any LLM involvement.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Loads the persisted graph built by builder.py for the current (repo_id, commit_hash).

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Exposed to the agent loop as the get_callers and get_callees tools inside app/agent/tools.py.
- Also used by app/diagrams/mermaid_generator.py to pull the subgraph to visualize.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `get_callers(function_name, max_hops=3)` | function name | list of calling functions | BFS backward through the graph, capped at 3 hops and a wall-clock timeout. |
| `get_callees(function_name, max_hops=3)` | function name | list of called functions | BFS forward, same limits. |

**Internal Workflow (pipeline steps inside this module)**

1. Load the cached graph for the current commit (in-memory cache keyed by repo_id+commit_hash, per the Advanced Blueprint's caching upgrade).
2. Run bounded BFS in the requested direction.
3. Return the result list; cache it in memory so repeated queries in the same session are instant.

**Data Contract**

- **Input:** function_name (string) + direction.
- **Output:** list[str] of related function names, each resolvable back to a file_path/line_range via the chunk metadata.

**Error Handling & Edge Cases**

- function_name not found in graph → return an empty list with a clear 'no such symbol at this commit' signal, not an exception.

> **Cost / Design Note:** Entirely free and near-instant once the in-memory graph cache (Advanced Blueprint Section 4) is added — this is why ACT-state graph tool calls cost zero Groq tokens.

---

### 20. `app/diagrams/mermaid_generator.py`

**Role:** Visualization rendering.

**Purpose**

Converts a NetworkX subgraph (centered on a requested entry point) into a Mermaid markdown diagram string that the Streamlit frontend renders directly.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives a bounded subgraph from app/graph/queries.py, scoped by entry_point and direction from the /diagram request.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Returned directly in the POST /diagram response body — no further backend processing.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `subgraph_to_mermaid(subgraph, entry_point)` | networkx subgraph | Mermaid markdown string | Maps nodes/edges to `graph TD` syntax; truncates diagrams beyond a readability threshold. |

**Internal Workflow (pipeline steps inside this module)**

1. Receive entry_point + direction from the request.
2. Ask graph/queries.py for the bounded subgraph (3-hop limit, same as get_callers/get_callees).
3. Serialize nodes/edges into Mermaid syntax.
4. Return the markdown string.

**Data Contract**

- **Input:** entry_point (string) + direction ('callers' | 'callees' | 'both').
- **Output:** {mermaid_markdown: str}.

**Error Handling & Edge Cases**

- Subgraph larger than the readability threshold → truncate with a 'N additional nodes not shown' note rather than emitting an unreadable diagram.

> **Cost / Design Note:** Zero LLM cost, pure string templating from graph data already computed for free.

---

## Layer 7 — Agentic Loop Engine (State-Machine Design)

### 21. `app/agent/loop.py`

**Role:** The core controller — replaces free-form prompting with an explicit, deterministic state machine.

**Purpose**

Owns the fixed state sequence INTAKE → PLAN → ACT → OBSERVE → DECIDE → FINALIZE → VERIFY → RESPOND described in the Advanced Architecture Blueprint. The LLM is only ever called inside a named state for a single narrow purpose; the state machine — not the model — decides transitions, retry limits, and termination.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Invoked by app/api/router.py's POST /chat handler.
- Reads MAX_ITERATIONS and MIN_CONFIDENCE_SCORE from app/config.py.
- INTAKE state reads sync_status from app/ingestion/metadata_store.py — a repo mid-sync returns a 'currently syncing' response instead of a stale answer.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- PLAN/DECIDE/FINALIZE states call the Groq LLM using the narrow, state-specific prompts in app/agent/prompts/.
- ACT state calls app/agent/tools.py, which wraps hybrid_search.py, reranker.py, and graph/queries.py.
- OBSERVE state calls app/agent/context_manager.py when the token budget is exceeded.
- VERIFY state calls app/agent/confidence.py (Guard v2).
- RESPOND state writes/reads app/agent/semantic_cache.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `run_chat_loop(repo_id, question, session_id)` | chat request | {answer, sources, confidence_score, gated} | The single public entry point; internally steps through the state machine with a hard iteration cap. |
| `_transition(state, context)` | current state, working memory | next state | Centralizes every allowed transition in one place so tests can assert no undeclared transition ever occurs (see Layer 8 test_state_machine.py). |

**Internal Workflow (pipeline steps inside this module)**

1. INTAKE: normalize the question, resolve commit_hash, check semantic_cache.py — on hit, skip straight to RESPOND.
2. PLAN: one narrow Groq call returns a single tool name + arguments (JSON only, not free text).
3. ACT: execute exactly one tool call via app/agent/tools.py — zero LLM cost.
4. OBSERVE: append the tool result to working memory; compress via context_manager.py only if the token budget is exceeded.
5. DECIDE: one narrow Groq call answers yes/no — 'is this enough to answer?' — looping back to PLAN on 'no', capped at MAX_ITERATIONS.
6. FINALIZE: one Groq call generates the final answer with markdown citations.
7. VERIFY: confidence.py runs its three deterministic checks; below MIN_CONFIDENCE_SCORE, the answer is replaced with a safe fallback.
8. RESPOND: cache the verified answer and return it through the API layer.

**Data Contract**

- **Input:** {repo_id, question, session_id}.
- **Output:** {answer, sources: [{file_path, function_name, start_line, end_line}], confidence_score, gated}.

**Error Handling & Edge Cases**

- MAX_ITERATIONS exceeded → force a transition to FINALIZE with whatever context has been gathered, never an infinite loop.
- Any tool failure inside ACT → caught and recorded as a failed observation, fed back into DECIDE rather than crashing the whole request.
- VERIFY failure (low confidence) → gated=true response, never a raw unverified answer reaching the user.

> **Cost / Design Note:** Per the zero-cost operating rules, this module enforces a hard cap of 6 Groq calls per question (PLAN + DECIDE per iteration, capped at 4 iterations, + FINALIZE) — ACT, OBSERVE (by default), and VERIFY are always free.

---

### 22. `app/agent/tools.py`

**Role:** Tool execution and schema validation (used inside the ACT state).

**Purpose**

Defines the explicit JSON schema for every callable tool (search_code, read_file, get_callers, get_callees, generate_diagram) and validates each tool call against its schema before execution — rejecting malformed calls before they can waste a Groq round-trip.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives a single {tool_name, arguments} object from loop.py's PLAN state output.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- search_code → app/retrieval/hybrid_search.py then app/retrieval/reranker.py.
- get_callers / get_callees → app/graph/queries.py.
- generate_diagram → app/diagrams/mermaid_generator.py.
- read_file → direct filesystem read from the locally cloned repo, scoped to the current commit.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `validate_call(tool_name, arguments)` | proposed call | validated call or ValidationError | Runs before execution; a schema mismatch is corrected or rejected without ever reaching Groq again. |
| `execute(tool_name, arguments)` | validated call | tool result object | Dispatches to the correct downstream module; wraps each call in retry logic (max 2 retries on transient I/O errors only). |

**Internal Workflow (pipeline steps inside this module)**

1. Receive the PLAN state's chosen tool + arguments.
2. Validate against the tool's JSON schema.
3. On valid input, execute and return a structured result.
4. On invalid input, return a structured error to OBSERVE instead of raising — the loop can still proceed to DECIDE with an 'attempt failed' note.

**Data Contract**

- **Input:** {tool_name: str, arguments: dict} matching one of five declared schemas.
- **Output:** {tool_name, result, success: bool, error: str|null}.

**Error Handling & Edge Cases**

- Unknown tool_name → immediate structured error, no execution attempt.
- Schema validation failure → structured error, no partial execution.

> **Cost / Design Note:** This validation layer is what prevents wasted/failed LLM round-trips on the Groq free tier — a bad tool call is caught in code, not by a second, wasted model call.

---

### 23. `app/agent/prompts/ (plan_prompt.py, decide_prompt.py, finalize_prompt.py, compress_prompt.py)`

**Role:** State-specific prompt definitions (replaces the single monolithic system_prompt.py).

**Purpose**

Instead of one exhaustive system prompt governing the whole conversation, each state that calls the LLM has its own small, single-purpose prompt — smaller token footprint per call and independently testable/versionable.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Imported directly by app/agent/loop.py inside the PLAN, DECIDE, FINALIZE, and (conditionally) OBSERVE/compress steps.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Each prompt's output feeds the next state: PLAN's output feeds ACT; DECIDE's output feeds the PLAN/FINALIZE branch; FINALIZE's output feeds VERIFY.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `plan_prompt(question, memory)` | question, prior context | prompt string requesting {tool_name, arguments} JSON only | Explicitly instructs the model to return nothing but JSON — no prose. |
| `decide_prompt(memory)` | accumulated tool results | prompt string requesting {needs_more: bool, reason: str} | Narrow yes/no decision, not open-ended reasoning. |
| `finalize_prompt(memory)` | accumulated tool results | prompt string requesting markdown answer with citations | Enforces the exact citation format `file_path:start_line-end_line` that confidence.py parses. |
| `compress_prompt(old_results)` | older tool outputs | prompt string requesting a dense summary paragraph | Used only by context_manager.py when the token budget is exceeded. |

**Internal Workflow (pipeline steps inside this module)**

1. loop.py selects the correct prompt module for its current state.
2. The prompt is filled with only the data relevant to that state (never the entire conversation history) to minimize tokens.
3. The LLM response is parsed against a strict expected shape (JSON for PLAN/DECIDE, markdown-with-citations for FINALIZE).

**Data Contract**

- **Input:** State-specific context (varies per prompt function).
- **Output:** A prompt string ready to send to Groq; parsing of the response is handled back in loop.py.

**Error Handling & Edge Cases**

- If FINALIZE's output is missing citations entirely, VERIFY (confidence.py) will score it near zero automatically — this is treated as a normal, expected VERIFY-stage rejection, not a crash.

> **Cost / Design Note:** Splitting the prompt this way directly reduces average tokens per Groq call, extending the free-tier budget compared to one large system prompt reused every turn.

---

### 24. `app/agent/semantic_cache.py`

**Role:** Pre-loop short-circuit (used in INTAKE and RESPOND).

**Purpose**

Embeds each incoming question and compares it against previously answered questions for the exact same commit_hash; a similarity above 0.95 returns the cached answer instantly at zero Groq cost.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Called first by loop.py's INTAKE state, before PLAN ever runs.
- Uses app/retrieval/embeddings.py to embed the question and app/retrieval/vector_store.py-style similarity search scoped by commit_hash.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- On a cache hit, the loop skips directly to RESPOND — PLAN/ACT/OBSERVE/DECIDE/FINALIZE/VERIFY never execute.
- On a cache miss, RESPOND writes the newly verified answer back here for future reuse.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `check_cache(question, repo_id, commit_hash)` | question + scope | cached answer or None | Only matches against entries scoped to the same commit_hash, so a code change automatically invalidates relevance. |
| `store(question, answer, repo_id, commit_hash)` | verified answer | none | Called only in RESPOND, only for answers that passed VERIFY (gated=false). |

**Internal Workflow (pipeline steps inside this module)**

1. INTAKE embeds the incoming question.
2. Compares against cached questions for this exact commit_hash only.
3. Similarity ≥ 0.95 → return the cached answer immediately.
4. Otherwise proceed through the full state machine; store the result at RESPOND if it passed VERIFY.

**Data Contract**

- **Input:** question (string) + repo_id + commit_hash.
- **Output:** Cached {answer, sources, confidence_score} or None.

**Error Handling & Edge Cases**

- Never caches a gated/low-confidence answer — this prevents a bad answer from being served repeatedly.

> **Cost / Design Note:** This is the single biggest cost lever under the zero-cost operating rules: every cache hit is a $0, instant answer.

---

### 25. `app/agent/context_manager.py`

**Role:** Token-budget enforcement (used inside OBSERVE).

**Purpose**

Monitors accumulated tool-result tokens in working memory during the loop; once a fixed per-state budget is exceeded, older tool results are condensed into a dense summary via a small secondary Groq call, preventing context-window overflow in FINALIZE.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Invoked by loop.py's OBSERVE state after each ACT result is appended to memory.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Its compressed summaries replace raw tool outputs inside the memory object that FINALIZE eventually reads.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `should_compress(memory)` | working memory | bool | Deterministic token-count check against a fixed budget — never left to the model's judgment. |
| `compress(memory)` | working memory | compressed memory | Uses compress_prompt.py for a single, narrow secondary Groq call summarizing only the oldest entries. |

**Internal Workflow (pipeline steps inside this module)**

1. After each OBSERVE, check accumulated token count against the fixed per-state budget.
2. If exceeded, compress only the oldest tool results (most recent stay verbatim for accuracy).
3. Replace the compressed entries in memory; proceed to DECIDE.

**Data Contract**

- **Input:** Working memory object (list of tool results with token counts).
- **Output:** Same memory object, with older entries replaced by shorter summaries.

**Error Handling & Edge Cases**

- Compression call fails → fall back to naive truncation (drop oldest entry) rather than blocking the loop.

> **Cost / Design Note:** Fixed token budgets here — not 'near the limit' heuristics — are what make memory footprint predictable per the Advanced Blueprint's Section 4 upgrade.

---

### 26. `app/agent/confidence.py`

**Role:** Hallucination Guard v2 (the VERIFY state).

**Purpose**

Runs three independent, deterministic checks against the FINALIZE state's answer — File Existence, Line-Range Bounds, and (new) Graph Consistency — and computes a 0–10 confidence score with zero additional LLM calls.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Receives the raw markdown answer from loop.py's FINALIZE state.
- Cross-references app/ingestion/metadata_store.py (file existence), the chunk metadata from chunker.py (line-range bounds), and app/graph/builder.py's persisted graph (function-name-still-exists check).

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Its score and possibly-replaced answer feed directly into loop.py's RESPOND state.
- A gated=true result is never written to semantic_cache.py.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `parse_citations(answer)` | markdown answer | list of {file_path, start_line, end_line, function_name} | Regex/markdown parser matching the exact citation format enforced by finalize_prompt.py. |
| `check_file_existence(citation)` | citation | bool | Confirms file_path exists in the current commit's index. |
| `check_line_bounds(citation)` | citation | bool | Confirms start_line/end_line fall within the real file's length. |
| `check_graph_consistency(citation)` | citation | bool | NEW: confirms the cited function_name is still a node in the current call graph (Advanced Blueprint Section 9). |
| `evaluate(answer)` | full answer | {score: float, gated: bool} | Aggregates all three checks with fixed penalty weights; gates below MIN_CONFIDENCE_SCORE (4.0). |

**Internal Workflow (pipeline steps inside this module)**

1. Parse every markdown citation out of the FINALIZE answer.
2. Run all three checks per citation.
3. Apply fixed penalties per failed check (File Existence −4.0, Line-Range −3.0, Graph Consistency −3.0).
4. If final score < MIN_CONFIDENCE_SCORE, strip the raw answer and substitute a safe fallback message; set gated=true.
5. Otherwise return the answer unmodified with gated=false.

**Data Contract**

- **Input:** Raw markdown answer string from FINALIZE.
- **Output:** {answer (possibly replaced), confidence_score: float, gated: bool}.

**Error Handling & Edge Cases**

- Citation format the parser cannot recognize at all → treated as a File Existence failure by default (fail closed, never fail open).

> **Cost / Design Note:** All three checks are deterministic Python/graph lookups — zero LLM cost — making VERIFY simultaneously the most safety-critical and the cheapest state in the whole loop.

---

### 27. `app/agent/onboarding_path.py`

**Role:** NEW — personalized learning-path generator.

**Purpose**

Builds an ordered, role-aware list of files a new developer should read first, using the existing call graph's centrality plus one narrow LLM call per file for a short rationale — the flagship differentiating feature from the Advanced Architecture Blueprint.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Reuses app/graph/builder.py's persisted graph and app/graph/queries.py's traversal utilities to find architecturally central files (highest in/out-degree).
- Reuses app/agent/loop.py's PLAN/FINALIZE machinery and app/agent/confidence.py's guard for the generated rationale text.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Serves POST /onboarding-path in app/api/router.py.
- Result cached per (repo_id, commit_hash, role) in semantic_cache.py-style storage so every new hire with the same role reuses the same computed path until the next re-index.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `rank_central_files(graph, role)` | graph, role filter | ordered file list | Filters centrality results by import patterns/path conventions matching the requested role (backend/frontend/ml). |
| `generate_rationale(file_path, role)` | file, role | short explanation string | One narrow Groq call per file explaining why it matters first; verified by confidence.py before being included. |
| `build_path(repo_id, role, experience_level)` | request params | ordered {file_path, why_it_matters, suggested_order, related_functions} | Top-level orchestrator combining ranking + rationale + verification. |

**Internal Workflow (pipeline steps inside this module)**

1. Load the persisted graph for the current commit.
2. Rank files by centrality, filtered to the requested role.
3. For each top-ranked file (bounded count, e.g. top 10), generate a short rationale via one Groq call.
4. Verify every file_path referenced actually exists in the current index (reusing confidence.py's File Existence check).
5. Cache the completed path per (repo_id, commit_hash, role) for reuse by future new hires.

**Data Contract**

- **Input:** {repo_id, role, experience_level}.
- **Output:** Ordered list of {file_path, why_it_matters, suggested_order, related_functions}.

**Error Handling & Edge Cases**

- Role filter matches zero files → fall back to overall centrality ranking (unfiltered) rather than returning an empty path.

> **Cost / Design Note:** This feature adds zero new infrastructure — it reuses the graph, loop engine, guard, and cache already built for Layers 6–7, keeping it inside the zero-cost plan.

---

## Layer 8 — Evaluation Suite

### 28. `eval/run_eval.py`

**Role:** Automated quality regression testing.

**Purpose**

Runs the Ragas framework's Faithfulness, Answer Relevancy, Context Precision, and Context Recall metrics over a fixed 'Golden Set' of known-good questions and expected citations — plus a new State-Path Consistency metric added for the loop redesign.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Exercises the full stack end-to-end: app/api/router.py → app/agent/loop.py → every Layer 5/6/7 module it touches.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Its results feed eval/compare_runs.py for regression detection between versions.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `run_golden_set()` | none (reads fixed question set) | per-question metric scores | Sends each golden question through the real /chat endpoint and scores the real response. |
| `state_path_consistency(question, repo_id, n_runs=3)` | question, repeat count | bool (consistent or not) | NEW: runs the identical question n times against the identical commit and asserts the state-transition sequence in loop.py's logs is identical every time. |

**Internal Workflow (pipeline steps inside this module)**

1. Load the Golden Set (question + expected citation set pairs).
2. For each question, call the real /chat endpoint.
3. Score Faithfulness/Relevancy/Precision/Recall via Ragas.
4. Additionally re-run each question 3 times and assert identical state-transition logs (the direct, measurable test of the Section-2 determinism goal).

**Data Contract**

- **Input:** Fixed Golden Set file (question + expected citations).
- **Output:** Structured metric report (per-question and aggregate scores).

**Error Handling & Edge Cases**

- A golden question now returns gated=true when it previously didn't → flagged as a regression requiring manual review, not silently ignored.

> **Cost / Design Note:** Costs real Groq calls per run since it exercises the live loop — run on a schedule (e.g. pre-release), not on every commit, to conserve free-tier quota.

---

### 29. `eval/compare_runs.py`

**Role:** Regression detection across versions.

**Purpose**

Diffs a new eval/run_eval.py report against the previous baseline report to surface any metric that dropped beyond a configured tolerance, including the new State-Path Consistency metric.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Reads two eval/run_eval.py report files: the current run and the last accepted baseline.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Its pass/fail output gates whether a new build is safe to deploy (used in the implementation-order checklist as the final acceptance step).

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `compare(baseline_report, new_report, tolerance)` | two reports + tolerance | list of regressions | Per-metric diff; flags any drop exceeding tolerance, with State-Path Consistency treated as a hard pass/fail (no tolerance) rather than a graded score. |

**Internal Workflow (pipeline steps inside this module)**

1. Load both reports.
2. Diff every shared metric.
3. Flag regressions beyond tolerance; treat any State-Path Consistency failure as an automatic hard-fail regardless of other scores.
4. Emit a pass/fail summary.

**Data Contract**

- **Input:** Two JSON eval reports.
- **Output:** {regressions: [...], overall_pass: bool}.

**Error Handling & Edge Cases**

- Missing baseline report on first run → treat the current run as the new baseline rather than failing.

> **Cost / Design Note:** Zero additional LLM cost — pure comparison of already-computed reports.

---

## Layer 9 — Frontend & Voice UX (New)

### 30. `app/api/state_stream.py`

**Role:** Live state-transition broadcaster (backend half of the loading-experience upgrade).

**Purpose**

Streams each real state transition of the running agent loop (INTAKE, PLAN, ACT, OBSERVE, DECIDE, FINALIZE, VERIFY) to the frontend as it happens, via Server-Sent Events, so the loading screen shows genuine progress instead of a generic spinner.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Hooked directly into app/agent/loop.py's `_transition(state, context)` function — every state change emits an event here, this module does not guess or simulate progress.
- Mounted as a new SSE endpoint (`GET /chat/stream/{session_id}`) inside app/api/router.py, alongside the existing POST /chat.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Consumed by the frontend's loading-experience component to render the current step, e.g. 'Searching the codebase...', 'Verifying citations...'.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `emit(session_id, state, detail)` | session id, current state, human label | none (pushes an SSE event) | Called once per state transition; detail is a short, pre-approved human-readable string per state (not raw internal state names). |
| `stream(session_id)` | session id | SSE event generator | FastAPI streaming response the frontend subscribes to for the duration of one /chat call. |

**Internal Workflow (pipeline steps inside this module)**

1. Frontend opens an SSE connection for the current session_id right before calling POST /chat.
2. As loop.py moves through each state, it calls emit() with a friendly label for that state.
3. Frontend renders each label the instant it arrives, in the same order the loop actually executes.
4. Connection closes automatically when RESPOND is reached and the final answer is delivered.

**Data Contract**

- **Input:** session_id (string) + state transitions pushed internally from loop.py.
- **Output:** SSE stream of {state, label, timestamp} events.

**Error Handling & Edge Cases**

- Client disconnects mid-stream → the underlying /chat request keeps running to completion server-side; only the live progress display is lost, never the answer itself.

> **Cost / Design Note:** Zero additional Groq cost — this only broadcasts state changes that are already happening; it adds no new LLM calls and works entirely off the existing state machine.

---

### 31. `frontend/loading_experience.py`

**Role:** State-aware progress UI (replaces the generic spinner).

**Purpose**

Renders the live state-transition events from app/api/state_stream.py as a short, friendly, rotating status line with a step indicator (e.g. 'Step 3 of 5 — Verifying citations'), plus a skeleton-text placeholder for the answer while FINALIZE is streaming.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Subscribes to GET /chat/stream/{session_id} the moment the user submits a question, before POST /chat's response arrives.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Replaced by the real answer + citations once RESPOND fires and POST /chat resolves.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `render_state(state, label)` | current state + label | UI update | Maps each backend state to a short label and a matching small icon/animation (search, graph, shield-check, etc.). |
| `render_skeleton()` | none | UI update | Shows grey placeholder lines shaped like text during FINALIZE, so the answer feels like it's 'arriving' rather than appearing all at once. |

**Internal Workflow (pipeline steps inside this module)**

1. On question submit, open the SSE stream and show step 1 immediately (no blank spinner ever shown with zero context).
2. On each event, update the visible label and step counter (e.g. 'Step 2 of 5').
3. When state == FINALIZE, switch to the skeleton-text placeholder.
4. On RESPOND, replace the skeleton with the real rendered answer and citations.

**Data Contract**

- **Input:** SSE event stream from state_stream.py.
- **Output:** Rendered UI state (Streamlit/React component tree), no data returned.

**Error Handling & Edge Cases**

- Stream drops before RESPOND → after a short timeout, fall back to a simple 'still working...' message rather than freezing on the last state shown.

> **Cost / Design Note:** This directly addresses the 'boring loading' feedback — every label shown is a real, currently-executing step, which builds trust instead of just occupying time.

---

### 32. `frontend/voice_input.py`

**Role:** Voice-to-text question input (free, browser-native).

**Purpose**

Adds a microphone button next to the chat input that uses the browser's built-in Web Speech API to transcribe spoken questions into text, which is then submitted through the exact same POST /chat path as typed questions — no new backend, no new cost.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Purely a frontend addition; triggered by user clicking the mic icon in the chat UI.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Transcribed text is submitted to app/api/router.py's POST /chat exactly like a typed question — Layers 2-8 are completely unaware voice was involved.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `start_listening()` | none | streaming transcript | Opens the browser's SpeechRecognition session; shows a live waveform animation while active. |
| `on_transcript_final(text)` | final transcript string | fills the chat input, optionally auto-submits | Lets the user confirm/edit before sending, or auto-send after a short pause. |
| `parse_voice_command(text)` | transcript | either a normal question or a shortcut action | Recognizes a small set of shortcut phrases (e.g. 'show diagram', 'explain again') and routes them to the matching existing endpoint instead of treating them as a new question. |

**Internal Workflow (pipeline steps inside this module)**

1. User clicks mic → browser asks for microphone permission (one-time).
2. Live transcript shown as the user speaks, with a waveform animation instead of a static 'listening...' label.
3. On finishing speech, the final transcript either auto-fills the input box or auto-submits, per user preference.
4. Voice shortcut phrases are matched before falling through to a normal /chat call.

**Data Contract**

- **Input:** Live microphone audio (handled entirely by the browser — never sent to the backend as audio).
- **Output:** Plain text string, submitted through the existing /chat contract.

**Error Handling & Edge Cases**

- Browser denies microphone permission → fall back gracefully to the text input, with a one-line explanation, never a broken UI state.
- Unsupported browser (no Web Speech API) → mic button hides itself automatically; text input remains fully functional.

> **Cost / Design Note:** 100% free — Web Speech API runs in-browser, no audio is ever uploaded or billed. This is why voice input costs nothing beyond development time.

---

### 33. `frontend/voice_output.py`

**Role:** Text-to-speech answer playback (free, browser-native).

**Purpose**

Optionally reads the agent's final answer aloud using the browser's built-in SpeechSynthesis API, enabling a hands-free, fully spoken conversation loop (ask by voice, hear the answer).

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Triggered automatically (if enabled) or manually once RESPOND delivers the final answer text from app/agent/loop.py.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Purely an output-side feature; produces no data consumed by any other module.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `speak(answer_text, language)` | final answer, language code | audio playback via browser | Strips markdown/citation syntax before speaking so the voice reads naturally instead of reading out raw brackets and file paths. |
| `toggle_voice_output(enabled)` | user preference | none | Persists the user's on/off choice for the session. |

**Internal Workflow (pipeline steps inside this module)**

1. Receive the final, verified answer text from the /chat response.
2. Strip markdown citation formatting into a speakable summary sentence (e.g. citations become 'according to sessions.py' rather than reading raw line numbers).
3. Play back via SpeechSynthesis, with a stop/pause control visible while speaking.

**Data Contract**

- **Input:** Final answer text (string) from the /chat response.
- **Output:** Spoken audio in-browser; no data sent anywhere.

**Error Handling & Edge Cases**

- Unsupported browser → the read-aloud button hides itself; text answer is unaffected.

> **Cost / Design Note:** Also free — runs entirely client-side. Combined with voice_input.py, this enables a fully hands-free demo, which is a strong live-demo differentiator.

---

### 34. `frontend/theme.py`

**Role:** Shared design system (colors, typography, layout) for a consistent, professional UI.

**Purpose**

Centralizes the visual brand (navy/blue/teal palette, typography scale, spacing, dark-mode-first defaults) used across every frontend screen, so the product looks like one cohesive tool rather than a default Streamlit app.

**Upstream Linkage (what feeds INTO this module — must exist before you build this one)**

- Loaded once at frontend startup; every other frontend module (chat view, loading_experience.py, voice controls, sidebar) imports shared style tokens from here.

**Downstream Linkage (what this module feeds — do not change this module's output shape without updating these)**

- Applied to the chat bubble layout, the sidebar (repo sync status, session history, onboarding-path panel), and the split-pane code/graph preview.

**Key Functions / Classes**

| Function / Class | Input | Output | Description |
|---|---|---|---|
| `get_theme(mode='dark')` | mode preference | theme token object (colors, fonts, spacing) | Dark mode is the default per the UX plan; light mode is a secondary toggle. |
| `apply_branding(component)` | a UI component | styled component | Injects consistent logo, color scheme, and font across chat, sidebar, and diagrams. |

**Internal Workflow (pipeline steps inside this module)**

1. Frontend boot loads the theme once.
2. Every screen/component pulls colors, spacing, and font sizes from the shared token object rather than hardcoding values.
3. Sidebar (session history, sync status, onboarding-path shortcut) and the split-pane chat/code-preview layout are built on top of the same tokens for visual consistency.

**Data Contract**

- **Input:** User's mode preference (dark/light), persisted per session.
- **Output:** A consistent set of design tokens applied across all frontend screens.

**Error Handling & Edge Cases**

- No theme preference found → default to dark mode, never an unstyled/default-browser look.

> **Cost / Design Note:** This is what turns the product from 'looks like a student project' into 'looks like a real product' — no backend cost, pure frontend investment.

---

## Global Linkage Map (quick reference)

| # | Module | Layer | Feeds Into |
|---|---|---|---|
| 1 | `app/config.py` | Configuration & Bootstrap | Every module in Layers 2–7 imports the shared `settings` object from here (api/auth. |
| 2 | `app/main.py` | Configuration & Bootstrap | Mounts app/api/router. |
| 3 | `app/api/router.py` | API Layer | /ingest → app/ingestion/clone. |
| 4 | `app/api/auth.py` | API Layer | Blocks all Layer 3–7 modules from ever executing on an unauthenticated request. |
| 5 | `app/api/rate_limiter.py` | API Layer | Prevents excess load from ever reaching app/agent/loop. |
| 6 | `app/ingestion/locking.py` | Ingestion Pipeline | Guards writes made by clone. |
| 7 | `app/ingestion/clone.py` | Ingestion Pipeline | Hands the local repo path to app/ingestion/file_filter. |
| 8 | `app/ingestion/file_filter.py` | Ingestion Pipeline | Passes the clean file list to app/parsing/tree_sitter_parser. |
| 9 | `app/ingestion/metadata_store.py` | Ingestion Pipeline | Read by GET /status/{repo_id}. |
| 10 | `app/parsing/tree_sitter_parser.py` | Parsing & Chunking | Passes structured AST nodes (with exact line ranges) to app/parsing/chunker. |
| 11 | `app/parsing/chunker.py` | Parsing & Chunking | Chunks go to app/retrieval/embeddings. |
| 12 | `app/retrieval/embeddings.py` | Retrieval & Storage | Embeddings are written to app/retrieval/vector_store. |
| 13 | `app/retrieval/vector_store.py` | Retrieval & Storage | Queried by app/retrieval/hybrid_search. |
| 14 | `app/retrieval/bm25_store.py` | Retrieval & Storage | Queried by hybrid_search. |
| 15 | `app/retrieval/hybrid_search.py` | Retrieval & Storage | Passes its fused top-N list to app/retrieval/reranker. |
| 16 | `app/retrieval/reranker.py` | Retrieval & Storage | Passes the final re-ordered, trimmed list to app/agent/loop. |
| 17 | `app/retrieval/query_expansion.py` | Retrieval & Storage | Its expanded keyword set is passed back into hybrid_search. |
| 18 | `app/graph/builder.py` | Graph Operations | The resulting graph is queried by app/graph/queries. |
| 19 | `app/graph/queries.py` | Graph Operations | Exposed to the agent loop as the get_callers and get_callees tools inside app/agent/tools. |
| 20 | `app/diagrams/mermaid_generator.py` | Graph Operations | Returned directly in the POST /diagram response body — no further backend processing. |
| 21 | `app/agent/loop.py` | Agentic Loop Engine (State-Machine Design) | PLAN/DECIDE/FINALIZE states call the Groq LLM using the narrow, state-specific prompts in app/agent/prompts/. |
| 22 | `app/agent/tools.py` | Agentic Loop Engine (State-Machine Design) | search_code → app/retrieval/hybrid_search. |
| 23 | `app/agent/prompts/` | Agentic Loop Engine (State-Machine Design) | Each prompt's output feeds the next state: PLAN's output feeds ACT; DECIDE's output feeds the PLAN/FINALIZE branch; FINALIZE's output feeds VERIFY. |
| 24 | `app/agent/semantic_cache.py` | Agentic Loop Engine (State-Machine Design) | On a cache hit, the loop skips directly to RESPOND — PLAN/ACT/OBSERVE/DECIDE/FINALIZE/VERIFY never execute. |
| 25 | `app/agent/context_manager.py` | Agentic Loop Engine (State-Machine Design) | Its compressed summaries replace raw tool outputs inside the memory object that FINALIZE eventually reads. |
| 26 | `app/agent/confidence.py` | Agentic Loop Engine (State-Machine Design) | Its score and possibly-replaced answer feed directly into loop. |
| 27 | `app/agent/onboarding_path.py` | Agentic Loop Engine (State-Machine Design) | Serves POST /onboarding-path in app/api/router. |
| 28 | `eval/run_eval.py` | Evaluation Suite | Its results feed eval/compare_runs. |
| 29 | `eval/compare_runs.py` | Evaluation Suite | Its pass/fail output gates whether a new build is safe to deploy (used in the implementation-order checklist as the final acceptance step). |
| 30 | `app/api/state_stream.py` | Frontend & Voice UX (New) | Consumed by the frontend's loading-experience component to render the current step, e. |
| 31 | `frontend/loading_experience.py` | Frontend & Voice UX (New) | Replaced by the real answer + citations once RESPOND fires and POST /chat resolves. |
| 32 | `frontend/voice_input.py` | Frontend & Voice UX (New) | Transcribed text is submitted to app/api/router. |
| 33 | `frontend/voice_output.py` | Frontend & Voice UX (New) | Purely an output-side feature; produces no data consumed by any other module. |
| 34 | `frontend/theme.py` | Frontend & Voice UX (New) | Applied to the chat bubble layout, the sidebar (repo sync status, session history, onboarding-path panel), and the split-pane code/graph preview. |

## Global Error Handling Standards (apply to every module above)

- **Fail fast at boundaries** — validate input shape at the API layer (Layer 2) before any downstream module runs.
- **Fail closed, not open** — the Hallucination Guard and all citation checks default to rejecting an unverifiable answer.
- **No silent partial failures** — every pipeline stage writes an explicit checkpoint (`SYNCED`, `FAILED`, etc.) to `metadata_store.py`.
- **One bad unit never fails a whole batch** — a single bad file/chunk/tool call is logged and skipped, never allowed to abort the whole request.
- **Every external (Groq) call has a bounded retry and a hard timeout.**
- **All client-facing errors follow one shape:** `{error_code, message}` — never a raw stack trace.

---

*End of MODULES.md — keep this file updated any time a module's function signature, contract, or linkage changes.*