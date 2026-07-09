# Build Log — Codebase Onboarding Agent

Tracks module build/verify status against `MODULES.md` spec.

| # | Module | Layer | Status | Verified |
|---|--------|-------|--------|----------|
| 1 | `app/config.py` | 1 | CONFIRMED | prior |
| 2 | `app/main.py` | 1 | CONFIRMED | prior |
| 3 | `app/api/router.py` | 2 | CONFIRMED | prior |
| 4 | `app/api/auth.py` | 2 | CONFIRMED | prior |
| 5 | `app/api/rate_limiter.py` | 2 | CONFIRMED | prior |
| 6 | `app/ingestion/locking.py` | 3 | CONFIRMED | prior |
| 7 | `app/ingestion/clone.py` | 3 | CONFIRMED | prior |
| 8 | `app/ingestion/file_filter.py` | 3 | CONFIRMED | prior |
| 9 | `app/ingestion/metadata_store.py` | 3 | CONFIRMED | prior |
| 10 | `app/parsing/tree_sitter_parser.py` | 4 | CONFIRMED | prior |
| 11 | `app/parsing/chunker.py` | 4 | CONFIRMED | prior |
| 12 | `app/retrieval/embeddings.py` | 5 | CONFIRMED | prior |
| **13** | **`app/retrieval/vector_store.py`** | **5** | **CONFIRMED** | **2026-07-09 — Chroma per-repo collections, replace upsert, INDEXING checkpoint** |
| 14 | `app/retrieval/bm25_store.py` | 5 | CONFIRMED | prior |
| 15 | `app/retrieval/hybrid_search.py` | 5 | CONFIRMED | prior |
| 16 | `app/retrieval/reranker.py` | 5 | CONFIRMED | prior |
| 17 | `app/retrieval/query_expansion.py` | 5 | CONFIRMED | prior |
| 18 | `app/graph/builder.py` | 6 | CONFIRMED | prior |
| **19** | **`app/graph/queries.py`** | **6** | **CONFIRMED** | **2026-07-09 — builder.get_graph + 60s TTL cache, bounded BFS** |
| **20** | **`app/diagrams/mermaid_generator.py`** | **6** | **CONFIRMED** | **2026-07-09 — generate_mermaid, sanitize_node_label, cycle highlight, POST /diagram wired, 7 module-20 tests** |
| **21** | **`app/agent/loop.py`** | **7** | **CONFIRMED** | **2026-07-09 — state machine run(), INTAKE→RESPOND, router /chat wired, 8 module-21 tests** |
| **22** | **`app/agent/tools.py`** | **7** | **CONFIRMED** | **2026-07-09 — validate_call/execute, Pydantic schemas, 5 tools wired, 10 module-22 tests** |
| **23** | **`app/agent/prompts/`** | **7** | **CONFIRMED** | **2026-07-09 — plan/decide/finalize/compress prompts, context_manager wired, 9 tests** |
| **24** | **`app/agent/semantic_cache.py`** | **7** | **CONFIRMED** | **2026-07-09 — check_cache/store, commit-scoped Chroma, 0.95 cosine threshold, 7 module-24 tests** |
| **25** | **`app/agent/context_manager.py`** | **7** | **CONFIRMED** | **2026-07-09 — should_compress/compress, 4000-token budget, tiktoken via chunker, 5 module-25 tests** |
| **26** | **`app/agent/confidence.py`** | **7** | **CONFIRMED** | **2026-07-09 — VERIFY guard v2, parse/evaluate + 3 deterministic checks, 9 module-26 tests** |
| **27** | **`app/agent/onboarding_path.py`** | **7** | **CONFIRMED** | **2026-07-09 — build_path, graph centrality + bounded rationales, JSON cache, router wired, 6 tests** |
| **28** | **`eval/run_eval.py`** | **8** | **CONFIRMED** | **2026-07-09 — run_golden_set, RAGAS + state-path consistency, /chat E2E, 7 tests** |
| **29** | **`eval/compare_runs.py`** | **8** | **CONFIRMED** | **2026-07-09 — compare(), tolerance + state-path hard-fail, 8 tests** |
| **30** | **`app/api/state_stream.py`** | **9** | **CONFIRMED** | **2026-07-09 — SSE state broadcaster, GET /chat/stream, loop hook, 5 tests** |
| **31** | **`frontend/loading_experience.py`** | **9** | **CONFIRMED** | **2026-07-09 — Streamlit state-aware progress UI, SSE consumer, 7 tests** |
| **32** | **`frontend/voice_input.py`** | **9** | **CONFIRMED** | **2026-07-09 — Web Speech mic input, shortcuts, waveform, 11 tests** |
| **33** | **`frontend/voice_output.py`** | **9** | **CONFIRMED** | **2026-07-09 — SpeechSynthesis TTS, citation strip, session toggle, 7 tests** |
| **34** | **`frontend/theme.py`** | **9** | **CONFIRMED** | **2026-07-09 — navy/blue/teal design system, dark default, branding, 9 tests** |

**All 34 modules CONFIRMED — build plan complete.**

## Module #13 assumptions

- **Store:** ChromaDB embedded/on-disk (`CHROMA_DB_PATH`) — zero hosted cost, native metadata filters, one collection per `repo_id`.
- **Default `top_k`:** 20 (caller override allowed).
- **Replace semantics:** `delete_repo()` then `create_collection()` on every `upsert_chunks()` with data.

## Module #19 assumptions

- **Default `max_depth`:** 3 hops (hard-clamped).
- **Cache TTL:** 60 seconds per `repo_id` in-process.
- **networkx:** `successors` / `predecessors` for deps/deps; manual bounded BFS for `get_subgraph`.

## Module #20 assumptions

- **Diagram type:** Mermaid flowchart (`graph TD` / `LR` / `BT` by direction).
- **Cycle style:** `-.->|cycle|` dashed edges when `get_cycle_info()` matches subgraph nodes.
- **Node IDs:** SHA1-suffixed stable IDs separate from escaped display labels.

## Module #21 assumptions

- **Context budget:** 4000 tokens (~16k chars) in OBSERVE via `context_manager_assemble` stub.
- **Groq model:** `settings.LLM_MODEL` for DECIDE and FINALIZE via `llm_client`.
- **DECIDE:** YES/NO single-token style verdict; max 8 output tokens.
- **Structural ACT:** `get_callers` / `get_callees` when question mentions callers/dependencies.
- **Integrations (CONFIRMED):** `#24 semantic_cache`, `#25 context_manager`, `#26 confidence` are fully wired into `loop.run()` — not stubs.

## Module #22 assumptions

- **Schema mechanism:** Pydantic v2 models per tool; ``TOOL_DEFINITIONS`` generated from ``model_json_schema()`` (single source of truth).
- **Transient retries:** ``OSError``, ``TimeoutError``, ``ConnectionError``, ``BlockingIOError``, ``urllib.error.URLError`` — max 2 retries in ``execute()`` (3 attempts).
- **read_file scope:** ``resolve_jailed_path`` under ``{REPOS_PATH}/{repo_id}/clone`` blocks ``../`` traversal.
- **Legacy:** ``execute_tool_with_retry`` retains 1 retry on any exception for Module 9a compatibility; ``search_web_docs`` / ``get_subgraph`` remain as legacy tools outside the five-spec ``validate_call`` set.

## Module #23 assumptions

- **JSON-only phrasing:** ``RESPOND WITH JSON ONLY. No markdown fences, no explanation, no prose before or after.``
- **Citation phrasing:** ``Cite EVERY factual claim using backticks with the exact format `file_path:start_line-end_line` (example: `src/auth/login.py:42-58`).``
- **Token caps in prompts:** DECIDE context truncated to 3000 chars; FINALIZE context to 12000 chars; compress payloads capped at 4000 chars each.
- **PLAN example JSON:** ``{"tool_name":"search_code","arguments":{"query":"...","top_k":5}}``
- **DECIDE example JSON:** ``{"needs_more": bool, "reason": str}``
- **loop.py:** not modified per build constraint; prompts exported for drop-in when PLAN/DECIDE/FINALIZE handlers switch from inline strings.

## Module #24 assumptions

- **Storage:** ChromaDB on-disk (`CHROMA_DB_PATH`), one collection per `(repo_id, commit_hash)` named `sc_{repo_id}_{commit_hash[:16]}` with `hnsw:space=cosine`.
- **Similarity:** `1 - distance` from Chroma cosine query; threshold `CACHE_HIT_SIMILARITY_THRESHOLD = 0.95`.
- **Embedding:** `app.retrieval.embeddings.embed()` only — zero Groq/LLM cost in this module.
- **TTL:** `SEMANTIC_CACHE_TTL_DAYS` (default 7) via metadata `timestamp`; expired entries deleted on read and via `sweep_expired_entries`.
- **gated guard:** `store()` rejects `gated=True` via explicit `gated` kwarg and `answer["gated"]` (defense in depth).
- **loop.py:** `semantic_cache_lookup` / `semantic_cache_store` delegate to the `SemanticCache` facade (production path).

## Module #25 assumptions

- **Token budget:** `OBSERVE_TOOL_RESULT_TOKEN_BUDGET = 4000` (fixed at import; matches loop `_DEFAULT_CONTEXT_TOKEN_BUDGET`).
- **Tokenizer:** `chunker.get_token_count` → `tiktoken` `cl100k_base`, char/4 fallback.
- **Keep recent:** `KEEP_RECENT_TOOL_RESULTS = 2` oldest compressed, newest verbatim.
- **Compression LLM:** `get_llm_client().create()` with 4.0s timeout, 2 attempts (retry-once), max 1000 output tokens.
- **Memory shape:** `list[dict]` with `content` blocks + optional `token_count` (same as legacy tool-result messages).
- **Fallback:** failed compression drops single oldest entry; never raises.
- **loop.py:** not modified; `compress_older_tool_results` retained for Module 9a compatibility.

## Module #26 assumptions

- **Citation regex:** ``r\`((?:[\w./\\\-@]+/)?[\w.\-]+\.[\w]{1,12}):(\d+)(?:-(\d+))?\`` — matches finalize_prompt ``file_path:start_line-end_line``.
- **function_name:** nearest preceding ``\`name()\`` backtick before each citation span.
- **File index:** ``metadata_store.get()`` sync gate + BM25/chunk metadata paths + clone file fallback.
- **Line bounds:** clone file line count first; chunk metadata (`start_line`/`end_line`) fallback.
- **Graph nodes:** ``builder.get_graph()`` nodes matched by ``name`` + ``path``.
- **Aggregation:** score = max(0, 10 − sum of per-check penalties across all citations); unparseable → file penalty only.
- **Gated fallback:** full answer replacement with ``GATED_FALLBACK_MESSAGE`` (no partial leak).
- **loop.py:** not modified; legacy ``validate_and_return`` / ``compute_confidence_score`` preserved for Module 9b.

## Module #27 assumptions

- **Centrality:** summed in-degree + out-degree per file path (networkx ``DiGraph`` nodes grouped by ``path`` attr).
- **Role patterns:** backend → ``app/``, ``api/``, ``.py``; frontend → ``frontend/``, ``components/``, ``.tsx/.jsx/.vue``; ml → ``ml/``, ``models/``, ``.ipynb``.
- **Top-N:** ``MAX_RATIONALE_FILES = 10``; experience_level maps junior/beginner→10, mid→8, senior→6.
- **Rationale LLM:** ``get_llm_client().create()``, 4.0s timeout, 2 attempts, 120 max tokens.
- **Cache:** JSON at ``{REPOS_PATH}/{repo_id}/.onboarding_path_cache/{commit}_{role}.json`` (semantic_cache-style namespace, separate from Module #24).
- **Router:** ``POST /onboarding-path`` returns structured ``OnboardingPathStep`` list via ``build_path()``.

## Module #28 assumptions

- **Golden Set:** ``data/golden_set.json`` (fallback ``tests/eval_set.json``); JSON list of ``{repo_id, question, ground_truth_files, ground_truth_answer_summary, expected_gated?}``.
- **RAGAS metrics:** ``faithfulness``, ``answer_relevancy``, ``context_precision``, ``context_recall`` via ``ragas.evaluate()``; judge LLM = Groq/Ollama via ``eval/ragas_providers.py``; embeddings = local HuggingFace ``settings.EMBEDDING_MODEL``.
- **E2E path:** ``TestClient`` → ``POST /chat`` → ``loop.run()`` (semantic cache disabled during eval).
- **State log:** ordered ``trace[].state`` strings from ``loop.run()`` — no loop.py changes required.
- **State-path runs:** 3 identical ``/chat`` calls per golden question; sequences compared for equality.
- **Gated regression:** ``expected_gated: false`` + actual ``gated: true`` → ``regression_flags.gated_flips`` (never averaged away).
- **Report shape:** ``{version, per_question, aggregate, ragas_scores, state_path_consistency, regression_flags}`` for ``compare_runs.py``.

## Module #29 assumptions

- **Default tolerance:** ``DEFAULT_TOLERANCE = 0.05`` absolute drop on 0–1 RAGAS scores.
- **Fields read:** ``ragas_scores`` (or ``aggregate.ragas_scores``), ``state_path_consistency.{rate,passed,total,failures}``, ``regression_flags.gated_flips``.
- **State-path:** hard fail when ``rate < 1.0`` or ``failures`` non-empty — no tolerance blending.
- **First run:** ``compare(None, new)`` or missing ``tests/eval_baseline.json`` → ``first_run_baseline_established=True``, ``overall_pass=True``.
- **Regression schema:** ``{metric, baseline_value, new_value, delta, kind, message}`` with ``kind`` ∈ ``tolerance_exceeded`` | ``state_path_hard_fail`` | ``gated_hard_fail``.
- **Zero LLM cost:** stdlib JSON + file I/O only; ``compare_eval_runs()`` retained for version-id router API.

## Module #30 assumptions

- **SSE transport:** FastAPI ``StreamingResponse`` + ``text/event-stream`` (no sse-starlette).
- **Routing:** in-memory ``queue.Queue`` per ``session_id`` (max 64 events); single-process lifecycle.
- **Labels:** fixed ``STATE_LABELS`` map for INTAKE→RESPOND (Unicode ellipsis in strings).
- **Termination:** internal ``STREAM_DONE_SENTINEL = "[DONE]"`` queued after RESPOND event.
- **Disconnect:** ``await request.is_disconnected()`` stops the async generator only; ``emit()`` never cancels ``loop.run()``.
- **loop.py:** minimal ``_transition()`` hook emits INTAKE once before first transition, then each ``nxt`` state.

## Module #31 assumptions

- **UI framework:** Streamlit (matches existing ``frontend/streamlit_app.py``).
- **Step total:** 7 (INTAKE through VERIFY); RESPOND shows delivery label without incrementing past 7.
- **Icons:** 💬 🧭 🔍 📋 ⚖️ ✍️ 🛡️ (+ ✅ on RESPOND).
- **Stall timeout:** ``STREAM_STALL_TIMEOUT_S = 15.0`` → ``Still working…`` fallback.
- **Final answer:** detected when ``POST /chat`` (``api_client.chat``) returns; skeleton cleared before render.
- **Bootstrap:** step 1 shown immediately with INTAKE label mirrored from Module #30 (no backend import).
- **SSE transport:** ``requests`` streaming GET; events consumed as ``{state, label, timestamp}`` with zero transformation.

## Module #32 assumptions

- **UI framework:** Streamlit ``components.html`` embeds browser Web Speech API JS.
- **Feature detect:** ``window.SpeechRecognition || window.webkitSpeechRecognition``; hide widget if absent.
- **Waveform:** ``getUserMedia`` + ``AnalyserNode`` + 24 animated bars (``requestAnimationFrame``).
- **Auto-submit pause:** ``AUTO_SUBMIT_PAUSE_MS = 1500`` after final transcript (editable textarea first).
- **Shortcuts:** explain again / ask again / repeat that → re-submit last user question; show diagram / generate diagram → ``GET /diagram`` (optional ``for <symbol>`` tail).
- **Streamlit bridge:** browser posts JSON via ``vi_payload`` query param; Python drains once per rerun.
- **Permission:** ``sessionStorage cn_voice_mic_granted`` avoids redundant prompts; denial shows one-line caption.

## Module #33 assumptions

- **UI framework:** Streamlit ``components.html`` embeds ``speechSynthesis`` / ``SpeechSynthesisUtterance``.
- **Citation transform:** ``file_path:start-end`` → ``according to <basename>`` (line numbers dropped).
- **Markdown strip:** headers, bold/italic markers, bullets/numbers, fenced code blocks, link URLs (keep label), leftover backticks.
- **Session persistence:** ``st.session_state["voice_output_enabled"]`` via ``toggle_voice_output()`` (not durable backend).
- **Stop control:** ``speechSynthesis.cancel()`` (immediate halt; not ``pause()``).
- **Upstream gate:** speak/read-aloud only for non-gated final answers after ``POST /chat`` returns.

## Module #34 assumptions

- **UI framework:** Streamlit (same as Modules #31–#33).
- **Palette (dark):** navy ``#0B1D36`` / ``#12263A`` / ``#1A3655``; blue ``#1D4ED8`` / ``#2563EB`` / ``#3B82F6``; teal ``#0D9488`` / ``#2DD4BF``.
- **Typography:** DM Sans + JetBrains Mono; scale xs→display (0.75rem→2.25rem).
- **Spacing:** 4px base unit → 4/8/12/16/24/32/48/64px.
- **Session key:** ``st.session_state["theme_mode"]``; missing → dark via ``DEFAULT_THEME_MODE``.
- **Branding:** ``apply_branding("global"|"chat"|"sidebar"|"diagram")`` injects CSS variables / branded HTML wrappers.
- **Load-once:** ``boot_theme()`` at startup via ``inject_styles()``; ``get_theme`` is ``lru_cache``'d.
