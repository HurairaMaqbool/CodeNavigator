# Golden Set Provenance Forensic Audit

## A. Executive Verdict

`DYNAMIC / RUN-SPECIFIC BENCHMARK`

While a static 25-query file exists at `data/golden_set.json`, both live experiment runners (`experiments/live/full_system_exp_a.py` and `experiments/live/naive_dense_baseline.py`) do **not** read from disk at runtime. Instead, both experiment runners define an embedded, in-code Python array (`BENCHMARK_QUERIES = [...]`) containing 27 queries (adding `gs_hall_001` and `gs_hall_002`).

## B. Canonical Benchmark Path

* **Static Repository Artifact (25 queries)**: `data/golden_set.json`
* **Runner Embedded Definition (27 queries)**: `experiments/live/full_system_exp_a.py:35-63` & `experiments/live/naive_dense_baseline.py:41-204`

## C. SHA-256 Hashes

* **SHA-256 of `data/golden_set.json` raw file**: `d32b509efddbf7acae416dfb774df2ebbdcd09bd6bb8e46953ebbb7bf7ae6635`
* **SHA-256 of Embedded 27-Query JSON (`json.dumps(BENCHMARK_QUERIES, indent=2)`)**: `5afb58a9ff44e2b9d4b5c10c06cb2ff6747a5882b3cf61b1923feb13f95c1ccd`

## D. Claimed Hash

`5afb58a9ff44e2b9d4b5c10c06cb2ff6747a5882b3cf61b1923feb13f95c1ccd`

## E. Hash Match

**YES** — The claimed benchmark hash `5afb58a9ff44e2b9d4b5c10c06cb2ff6747a5882b3cf61b1923feb13f95c1ccd` is reproduced exactly by computing `hashlib.sha256(json.dumps(BENCHMARK_QUERIES, indent=2).encode("utf-8")).hexdigest()` on the 27-query Python array hard-coded in the runner scripts.

## F. Complete 27-Query Comparison (EXP-A vs EXP-B Raw Artifacts)

| query_id | EXP-A Raw Question | EXP-B Raw Question | Identical? |
| :--- | :--- | :--- | :---: |
| `gs_ingest_001` | How does the ingestion pipeline handle large repositories? | How does the ingestion pipeline handle large repositories? | YES |
| `gs_ingest_002` | What happens if the GitHub webhook receives a push event on a non-default branch? | What happens if the GitHub webhook receives a push event on a non-default branch? | YES |
| `gs_ingest_003` | Which file extensions are allowed during the chunking phase? | Which file extensions are allowed during the chunking phase? | YES |
| `gs_ingest_004` | How is the ingestion lock implemented to prevent concurrent ingestion of the same repo? | How is the ingestion lock implemented to prevent concurrent ingestion of the same repo? | YES |
| `gs_ingest_005` | What is the role of metadata_store.mark_synced? | What is the role of metadata_store.mark_synced? | YES |
| `gs_retrieval_001` | How does hybrid search combine BM25 and vector scores? | How does hybrid search combine BM25 and vector scores? | YES |
| `gs_retrieval_002` | Where is the BM25 index persisted on disk? | Where is the BM25 index persisted on disk? | YES |
| `gs_retrieval_003` | Does the pipeline use a cross-encoder reranker? | Does the pipeline use a cross-encoder reranker? | YES |
| `gs_retrieval_004` | What happens if query expansion LLM request times out? | What happens if query expansion LLM request times out? | YES |
| `gs_retrieval_005` | What vector database is used for semantic search? | What vector database is used for semantic search? | YES |
| `gs_agent_001` | How does the agent avoid executing duplicate tool calls? | How does the agent avoid executing duplicate tool calls? | YES |
| `gs_agent_002` | What determines if an agent's answer is 'gated' due to hallucination? | What determines if an agent's answer is 'gated' due to hallucination? | YES |
| `gs_agent_003` | How long is a semantic cache entry valid? | How long is a semantic cache entry valid? | YES |
| `gs_agent_004` | How are LLM rate limits handled in the agent loop? | How are LLM rate limits handled in the agent loop? | YES |
| `gs_agent_005` | What happens if an individual tool execution fails during the agent loop? | What happens if an individual tool execution fails during the agent loop? | YES |
| `gs_graph_001` | How does the graph builder detect circular dependencies? | How does the graph builder detect circular dependencies? | YES |
| `gs_graph_002` | What is the maximum number of nodes allowed in the graph? | What is the maximum number of nodes allowed in the graph? | YES |
| `gs_graph_003` | How does get_subgraph limit the depth of the returned graph? | How does get_subgraph limit the depth of the returned graph? | YES |
| `gs_graph_004` | What format is the graph converted to for visualization? | What format is the graph converted to for visualization? | YES |
| `gs_graph_005` | Are class methods linked to their parent classes in the call graph? | Are class methods linked to their parent classes in the call graph? | YES |
| `gs_api_001` | How is rate limiting implemented on the API endpoints? | How is rate limiting implemented on the API endpoints? | YES |
| `gs_api_002` | What validation does the /chat endpoint perform on the user question? | What validation does the /chat endpoint perform on the user question? | YES |
| `gs_api_003` | How does the API handle an unhandled exception globally? | How does the API handle an unhandled exception globally? | YES |
| `gs_api_004` | Is the /ingest endpoint synchronous or asynchronous? | Is the /ingest endpoint synchronous or asynchronous? | YES |
| `gs_api_005` | What is the return structure of the /eval/status endpoint? | What is the return structure of the /eval/status endpoint? | YES |
| `gs_hall_001` | Is the class InvalidUrlException defined in app/api/router.py? | Is the class InvalidUrlException defined in app/api/router.py? | YES |
| `gs_hall_002` | Does app/graph/builder.py define a CypherQueryExecutor class? | Does app/graph/builder.py define a CypherQueryExecutor class? | YES |

* **Identical Question Count**: 27 / 27 (100%)
* **Different Question Count**: 0 / 27 (0%)
* **Missing / Duplicate IDs**: None
* **Ground-Truth Mismatches**: 0

## G. Seven Specific Queries Audit

Forensic inspection of `gs_agent_001` through `gs_agent_005`, `gs_api_001`, and `gs_api_003` confirms that the question text in `exp_a_full_system_live.json` and `exp_b_naive_dense_rag_live.json` is **100% identical**:

1. `gs_agent_001`: `"How does the agent avoid executing duplicate tool calls?"` (Identical in A & B)
2. `gs_agent_002`: `"What determines if an agent's answer is 'gated' due to hallucination?"` (Identical in A & B)
3. `gs_agent_003`: `"How long is a semantic cache entry valid?"` (Identical in A & B)
4. `gs_agent_004`: `"How are LLM rate limits handled in the agent loop?"` (Identical in A & B)
5. `gs_agent_005`: `"What happens if an individual tool execution fails during the agent loop?"` (Identical in A & B)
6. `gs_api_001`: `"How is rate limiting implemented on the API endpoints?"` (Identical in A & B)
7. `gs_api_003`: `"How does the API handle an unhandled exception globally?"` (Identical in A & B)

In `gs_agent_001`, the model answer `"The provided codebase context does not contain any mechanism or logic for avoiding duplicate tool calls"` directly addresses the prompt question `"How does the agent avoid executing duplicate tool calls?"`.

## H. Benchmark Loading Trace

* **EXP-A Loading Trace**: `experiments/live/full_system_exp_a.py` → Reads inline Python list `BENCHMARK_QUERIES` → Computes SHA-256 hash of `json.dumps(BENCHMARK_QUERIES, indent=2)` → Iterates queries to `run_agent_loop(repo_id, question)`.
* **EXP-B Loading Trace**: `experiments/live/naive_dense_baseline.py` → Reads inline Python list `BENCHMARK_QUERIES` → Iterates queries to `chroma_vector_query(...)` & `get_llm_client()`.

## I. Git Provenance

* `data/golden_set.json`: Tracked in git repository (Contains original 25 queries).
* `experiments/live/full_system_exp_a.py`: Tracked in git repository.
* `experiments/live/naive_dense_baseline.py`: Tracked in git repository.

## J. Dynamic Generation Analysis

**NO** — Questions are not randomly generated or dynamic templates at runtime. However, because the 27 benchmark queries are defined inline in the python runner scripts rather than loaded from a single shared static JSON file on disk, maintenance requires keeping both runner scripts synchronized.

## K. Research Consequence

Both EXP-A and EXP-B executed against **100% identical question texts, ground-truth files, and query IDs** across all 27 benchmark items. Therefore, the paired benchmark comparison between EXP-A and EXP-B is **valid and aligned**.
