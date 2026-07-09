# PROJECT_BLUEPRINT.md — Codebase Onboarding Agent

> **What this file is:** The single high-level reference for the whole system — architecture, the agentic state machine, all workflows, the zero-cost operating rules, and the roadmap. Read this file first, before `MODULES.md`.
>
> **What `MODULES.md` is:** The detailed, file-by-file specification (functions, contracts, linkage) for every module named in this blueprint.
>
> **How to use both files with an AI coding agent (e.g. Claude Code):** Always load `PROJECT_BLUEPRINT.md` + `MODULES.md` into context before asking for any code change. When asking for a specific module, name it exactly as written here (e.g. `app/agent/loop.py`) so the AI locates the correct spec in `MODULES.md` instead of guessing or inventing new structure. Never let the AI change a module's input/output contract without also updating `MODULES.md`.

---

## 1. What This Project Is

An agentic, graph-augmented Retrieval-Augmented Generation (RAG) pipeline that ingests a codebase, indexes it three ways (semantic, lexical, structural), and answers developer questions about it through a **deterministic, loop-based agent** — not free-form prompting.

| Layer | Tech |
|---|---|
| Backend | Python / FastAPI |
| Frontend | Streamlit |
| Vector Store | ChromaDB + BM25 |
| Graph Engine | NetworkX |
| LLM Provider | Groq (free tier only — see Section 6) |

---

## 2. Core Design Principle: Loop Structure, Not Prompt-Only Reasoning

The single most important architectural decision in this project:

> **The LLM never decides how the agent behaves. An explicit state machine, written in code, decides that. The LLM is only called inside a named state, for one narrow purpose, and always returns a constrained shape (JSON or a strict citation format) — never free-form control.**

### Why this matters

| Aspect | Prompt-Only (avoid) | Loop-Structured (this project) |
|---|---|---|
| Decision authority | LLM decides everything from free text | State machine decides transitions; LLM fills in content only |
| Stopping condition | LLM decides when it's "done" | Hard iteration cap (`MAX_ITERATIONS`) + explicit `FINALIZE` state |
| Debuggability | Hard to trace why a path was taken | Every state transition is logged with a reason code |
| Cost control | Unbounded tool calls possible | Tool-call budget enforced per state |
| Consistency | Same question can behave differently each run | Same question always follows the same state path |

This is also the product's **moat**: a competitor can copy prompt text easily, but cannot easily copy engineered control flow + graph reasoning + deterministic verification.

---

## 3. The Agentic Loop — State Machine (`app/agent/loop.py`)

### 3.1 States

| State | Responsibility | Calls Groq? |
|---|---|---|
| `INTAKE` | Normalize the question, resolve `repo_id` + `commit_hash`, check semantic cache | No |
| `PLAN` | Return a single `{tool_name, arguments}` JSON — no prose | Yes (small, JSON-only) |
| `ACT` | Execute exactly one tool call | No |
| `OBSERVE` | Attach tool result to memory; compress only if the token budget is exceeded | Maybe (compression only) |
| `DECIDE` | Answer yes/no: "is this enough to answer?" | Yes (yes/no + reason) |
| `FINALIZE` | Write the final markdown answer with citations | Yes |
| `VERIFY` | Run the Hallucination Guard (3 deterministic checks) | No |
| `RESPOND` | Cache and return the verified answer, or the gated fallback | No |

### 3.2 Transition Rules (pseudocode)

```
state = INTAKE
iterations = 0
MAX_ITERATIONS = 4          # hard cap, not model-decided

while state != RESPOND:
    if iterations > MAX_ITERATIONS:
        state = FINALIZE     # force an answer, never loop forever

    if state == INTAKE:
        cached = semantic_cache.check(question, commit_hash)
        state = RESPOND if cached else PLAN

    elif state == PLAN:
        plan = llm_call(PLAN_PROMPT, question)      # returns tool name only
        state = ACT

    elif state == ACT:
        result = tools.run(plan.tool_name, plan.args)
        iterations += 1
        state = OBSERVE

    elif state == OBSERVE:
        memory.append(result)
        if memory.token_count() > THRESHOLD:
            memory.compress()      # secondary LLM call, summarizes only
        state = DECIDE

    elif state == DECIDE:
        needs_more = llm_call(DECIDE_PROMPT, memory)  # yes/no + tool
        state = PLAN if needs_more else FINALIZE

    elif state == FINALIZE:
        answer = llm_call(FINALIZE_PROMPT, memory)
        state = VERIFY

    elif state == VERIFY:
        score = confidence.evaluate(answer)
        answer = answer if score >= MIN_CONFIDENCE_SCORE else fallback()
        state = RESPOND
```

**Cost ceiling per question:** ~4–6 Groq calls worst case (`PLAN` + `DECIDE` per iteration, capped at 4 iterations, + `FINALIZE`). `ACT`, `OBSERVE` (default), and `VERIFY` cost zero LLM calls.

Full per-module implementation details for every state's supporting file (`tools.py`, `prompts/`, `semantic_cache.py`, `context_manager.py`, `confidence.py`, `onboarding_path.py`) are in `MODULES.md` under **Layer 7 — Agentic Loop Engine**.

---

## 4. The Eight Layers (build order)

| Layer | Responsibility | Runs During |
|---|---|---|
| 1. Configuration & Bootstrap | Load + validate all settings; start FastAPI app | Process startup (once) |
| 2. API Layer | Auth, rate limiting, request routing | Every HTTP request |
| 3. Ingestion Pipeline | Clone, filter, lock, checkpoint repo state | `/ingest` and webhook sync |
| 4. Parsing & Chunking | AST extraction, logical chunking | During ingestion |
| 5. Retrieval & Storage | Embeddings, ChromaDB, BM25, fusion, reranking | During ingestion (write) + `/chat` (read) |
| 6. Graph Operations | Call-graph build, traversal, diagram rendering | During ingestion (write) + `/chat`, `/diagram` (read) |
| 7. Agentic Loop Engine | The state machine that answers questions safely | `/chat` and `/onboarding-path` |
| 8. Evaluation Suite | Automated regression testing of the whole stack | Pre-release / scheduled |
| 9. Frontend & Voice UX (New) | State-aware loading feedback, voice input/output, design system | Every user session |

**Rule:** each layer only ever depends on layers *above* it, never below. Layer 7 assumes Layers 3–6 already produced a clean, indexed, graph-linked codebase. Layer 9 is presentation-only — it never changes what Layers 1–8 compute, only how it's shown/heard. Full module list per layer is in `MODULES.md`.

---

## 5.5 Layer 9 — Frontend & Voice UX (New)

Three specific upgrades, all zero additional Groq/API cost:

### A. State-Aware Loading (replaces the generic spinner)

The agent loop (Section 3) already moves through named, real states — `INTAKE → PLAN → ACT → OBSERVE → DECIDE → FINALIZE → VERIFY`. Instead of a spinner, the frontend now shows **which real step is currently running**, live:

```
User submits question
      |
      v
Frontend opens SSE stream --> app/api/state_stream.py
      |                              |
      |                     (emits on every real
      |                      state transition from
      |                      app/agent/loop.py)
      v                              |
frontend/loading_experience.py <-----+
  "Step 1 of 5 - Searching the codebase..."
  "Step 2 of 5 - Checking function relationships..."
  "Step 3 of 5 - Writing the answer..." (skeleton-text placeholder)
  "Step 4 of 5 - Verifying citations..."
      |
      v
Final answer replaces the skeleton once RESPOND fires
```

**Why this works:** every label shown is a real, currently-executing step (pulled straight from `loop.py`'s actual state), not a fake progress bar — so it builds trust instead of just occupying time.

### B. Voice Input & Output (browser-native, 100% free)

```
Mic click -> frontend/voice_input.py (Web Speech API, in-browser)
                    |
        live waveform animation while listening
                    |
          transcript fills chat input
                    |
        (voice shortcuts like "show diagram" route
         directly to the matching existing endpoint)
                    |
       submitted through the SAME POST /chat contract
       as a typed question -- Layers 2-8 never know
       the input was spoken
                    |
                    v
        Final answer optionally read aloud by
        frontend/voice_output.py (SpeechSynthesis API)
```

No audio is ever uploaded to the backend or billed — both directions run entirely in the browser.

### C. Professional Design System

`frontend/theme.py` centralizes one consistent look (dark-mode-first, navy/blue/teal palette) across the chat view, sidebar (sync status, session history, onboarding-path shortcut), and the split-pane chat/code-preview layout — so the product reads as one cohesive tool.

Full module specs (functions, contracts, error handling) for all five Layer 9 modules — `app/api/state_stream.py`, `frontend/loading_experience.py`, `frontend/voice_input.py`, `frontend/voice_output.py`, `frontend/theme.py` — are in `MODULES.md`.

---

## 5. Workflows

### 5.1 Ingestion Pipeline (resumable state machine)

```
PENDING -> CLONING -> FILTERING -> PARSING -> INDEXING -> SYNCED
                 \            \           \
                  +--> FAILED  +--> FAILED  +--> FAILED (retriable, resumes at same stage)
```

Each stage writes its own checkpoint to `app/ingestion/metadata_store.py`. On retry, the pipeline resumes at the last successful checkpoint instead of restarting from zero (important for large repos on a free/local setup).

### 5.2 Agentic Chat Loop (end-to-end)

```
User -> /chat -> INTAKE (cache check)
                    |
         [cache HIT] --------------------------> RESPOND (instant, $0 cost)
                    |
         [cache MISS]
                    v
                  PLAN  (1 Groq call: pick a tool)
                    v
                  ACT   (0 Groq calls: run tool, e.g. search_code)
                    v
                OBSERVE (0-1 Groq calls: compress only if needed)
                    v
                DECIDE (1 Groq call: enough info? yes/no)
               /                          \
     [no, loop] back to PLAN      [yes] -> FINALIZE (1 Groq call: write answer)
     (capped at 4 iterations)                 v
                                            VERIFY (0 Groq calls: deterministic check)
                                                v
                                            RESPOND (cache + return)
```

### 5.3 Onboarding Path Generator (flagship feature)

```
1. get_callers/get_callees used to find the graph's most "central" files
   (highest in-degree/out-degree = architectural entry points)
2. Filter centrality results by role (backend/frontend/ml) using
   file path + import patterns already captured during ingestion
3. PLAN/FINALIZE states (same loop engine) generate a short
   "why this file matters first" explanation per entry
4. Guard verifies every file path in the path actually exists in the index
5. Result cached per (repo, commit, role) -- reused for every new hire
   with that role until the next webhook-triggered re-index
```

Reuses 100% of existing infrastructure (graph, loop engine, guard, cache) — no new paid infra required.

### 5.4 Webhook Auto-Sync (self-healing)

```
GitHub Webhook -> Verify HMAC -> Re-ingest (Workflow 5.1 state machine)
                                        |
                                 invalidate_cache(repo_id)
                                        |
                             compare new commit_hash vs
                             metadata_store's last known hash
                                        |
                             if a webhook was missed (hash mismatch
                             found on next /chat call), auto-trigger
                             re-ingest before answering
```

---

## 6. Hallucination Guard v2 (the `VERIFY` state)

Three independent, deterministic checks — zero additional LLM calls:

| Check | What it verifies | Penalty if failed |
|---|---|---|
| File Existence | Every cited `file_path` exists in the current commit's index | −4.0 confidence points |
| Line-Range Bounds | Cited `start_line`/`end_line` fall within the real file length | −3.0 confidence points |
| Graph Consistency (new) | Cited function names still exist as nodes in the current call graph | −3.0 confidence points |

`MIN_CONFIDENCE_SCORE` gate = **4.0**. Below this, the raw answer is stripped and replaced with a safe fallback (`gated: true`), and the answer is **never** written to the semantic cache.

---

## 7. Zero-Cost Operating Rules (Groq-only, no paid services, no local heavy models)

| Component | Tool | Cost |
|---|---|---|
| LLM (agent brain) | Groq free tier (Llama 3.1/3.3, Mixtral) | $0 |
| Vector store | ChromaDB (self-hosted) | $0 |
| Keyword search | BM25 (pure Python) | $0 |
| Graph engine | NetworkX | $0 |
| Embeddings | sentence-transformers (HuggingFace, CPU) | $0 |
| Reranker | Cross-Encoder (HuggingFace, CPU) | $0 |
| Parsing | Tree-sitter grammars | $0 |
| Backend / Frontend | FastAPI / Streamlit (local) | $0 |

**Rules that keep it free as usage grows:**

1. Cap LLM calls per question at 6 — enforced by the state machine, never left to the model.
2. `ACT`, `OBSERVE` (default), and `VERIFY` never call an LLM.
3. Semantic cache hit rate is the primary cost lever — every cache hit is a $0 answer.
4. Reranker and embeddings always run locally (HuggingFace, CPU) — never routed through Groq.
5. Rate limiter (`app/api/rate_limiter.py`) stays tight until real paying usage justifies raising it.

---

## 8. Implementation Roadmap

| Phase | Duration | Deliverable |
|---|---|---|
| Phase 1 | Week 1–2 | Refactor `app/agent/loop.py` into the explicit state machine; split `system_prompt.py` into 4 state-specific prompts. |
| Phase 2 | Week 3 | Upgrade `confidence.py` to the 3-check `VERIFY` state; add state-path logging. |
| Phase 3 | Week 4–5 | Build the Onboarding Path Generator endpoint and workflow. |
| Phase 4 | Week 6 | Add webhook reconciliation self-healing; add Go/Java/Rust Tree-sitter grammars. |
| Phase 5 | Week 7–8 | Add the "State-Path Consistency" Ragas metric to `eval/run_eval.py`; run full regression via `compare_runs.py`. |
| Phase 6 | Week 9–10 | Build Layer 9: SSE state-stream + state-aware loading UI, browser-native voice input/output, and the shared design system (dark-mode-first). |

Every phase uses only tools already free in the stack — no new spend at any phase.

---

## 9. Path to a Paid Product (business layer, not code — tracked separately from engineering)

1. Reliability proof: run on 20–30 real repos, publish near-zero hallucination rate.
2. On-premise / self-hosted deployment option (companies won't send proprietary code to a random cloud tool).
3. SSO + team accounts + audit logs.
4. SLA-backed uptime + support.
5. Clear differentiation vs. Cursor/Copilot/Sourcegraph: verifiable citations + the Onboarding Path Generator, positioned for new-hire ramp-up specifically.
6. 2–3 paying pilot customers before any broader launch.

---

## 10. File Map — Where Everything Lives

See `MODULES.md` for the full file-by-file specification. Quick index by layer:

- **Layer 1:** `app/config.py`, `app/main.py`
- **Layer 2:** `app/api/router.py`, `app/api/auth.py`, `app/api/rate_limiter.py`
- **Layer 3:** `app/ingestion/locking.py`, `clone.py`, `file_filter.py`, `metadata_store.py`
- **Layer 4:** `app/parsing/tree_sitter_parser.py`, `chunker.py`
- **Layer 5:** `app/retrieval/embeddings.py`, `vector_store.py`, `bm25_store.py`, `hybrid_search.py`, `reranker.py`, `query_expansion.py`
- **Layer 6:** `app/graph/builder.py`, `queries.py`, `app/diagrams/mermaid_generator.py`
- **Layer 7:** `app/agent/loop.py`, `tools.py`, `prompts/` (plan/decide/finalize/compress), `semantic_cache.py`, `context_manager.py`, `confidence.py`, `onboarding_path.py`
- **Layer 8:** `eval/run_eval.py`, `compare_runs.py`
- **Layer 9 (New):** `app/api/state_stream.py`, `frontend/loading_experience.py`, `frontend/voice_input.py`, `frontend/voice_output.py`, `frontend/theme.py`

---

## 11. Golden Rule for Any Future Update

> When updating any single module, **never change its Data Contract (input/output shape) without also updating every module listed in its Downstream Linkage in `MODULES.md`.** This is the rule that prevents the AI (or a human) from silently breaking a module three layers away.

---

*End of PROJECT_BLUEPRINT.md — keep this file and `MODULES.md` in sync with the actual codebase at all times.*