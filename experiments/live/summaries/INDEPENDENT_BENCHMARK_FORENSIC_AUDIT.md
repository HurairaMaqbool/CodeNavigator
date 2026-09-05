# INDEPENDENT BENCHMARK FORENSIC AUDIT REPORT

## 1. Executive Verdict

### FINAL VERDICT: **A — VALID PAIRED BENCHMARK**

Direct string-level inspection of raw experiment artifacts and runner source files on disk establishes that EXP-A and EXP-B executed against **100% identical question texts, ground-truth file assignments, and query ID orderings** across all 27 benchmark queries.

## 2. Files Inspected

* `data/golden_set.json` (Static repository benchmark file, 25 queries)
* `experiments/live/full_system_exp_a.py` (EXP-A execution runner script)
* `experiments/live/naive_dense_baseline.py` (EXP-B execution runner script)
* `experiments/live/raw/exp_a_full_system_live.json` (EXP-A raw output artifact, 27 queries)
* `experiments/live/raw/exp_b_naive_dense_rag_live.json` (EXP-B raw output artifact, 27 queries)

## 3. Canonical Benchmark Candidates

1. **`data/golden_set.json`**: Contains 25 queries created on 2026-06-26. Lacks `gs_hall_001` and `gs_hall_002`.
2. **Runner In-Code Arrays (`BENCHMARK_QUERIES`)**: Embedded Python lists in `full_system_exp_a.py` and `naive_dense_baseline.py`. Contains 27 queries, adding the two hallucination evaluation queries.

## 4. EXP-A Benchmark Loading Trace

```text
experiments/live/full_system_exp_a.py (lines 35-63)
    ↓ (reads BENCHMARK_QUERIES python list)
hashlib.sha256(json.dumps(BENCHMARK_QUERIES, indent=2))
    ↓ (computes benchmark_hash '5afb58a9...')
run_agent_loop(repo_id, question)
    ↓ (executes full agent pipeline for each item)
experiments/live/raw/exp_a_full_system_live.json
```

## 5. EXP-B Benchmark Loading Trace

```text
experiments/live/naive_dense_baseline.py (lines 41-204)
    ↓ (reads BENCHMARK_QUERIES python list)
chroma_vector_query(repo_id, question, top_k=5)
    ↓ (retrieves top-5 dense chunks directly)
get_llm_client().complete(...)
    ↓ (generates answer with Groq LLM)
experiments/live/raw/exp_b_naive_dense_rag_live.json
```

## 6. Complete 27-Query Comparison Matrix

| query_id | A question | B question | question match | A ground truth | B ground truth | GT match |
| --- | --- | --- | :---: | --- | --- | :---: |
| `gs_agent_001` | How does the agent avoid executing duplicate tool calls? | How does the agent avoid executing duplicate tool calls? | TRUE | app/agent/loop.py, app/agent/tools.py | app/agent/loop.py, app/agent/tools.py | TRUE |
| `gs_agent_002` | What determines if an agent's answer is 'gated' due to hallucination? | What determines if an agent's answer is 'gated' due to hallucination? | TRUE | app/agent/claim_verification.py, app/agent/confidence.py, app/agent/loop.py | app/agent/claim_verification.py, app/agent/confidence.py, app/agent/loop.py | TRUE |
| `gs_agent_003` | How long is a semantic cache entry valid? | How long is a semantic cache entry valid? | TRUE | app/agent/semantic_cache.py, app/config.py | app/agent/semantic_cache.py, app/config.py | TRUE |
| `gs_agent_004` | How are LLM rate limits handled in the agent loop? | How are LLM rate limits handled in the agent loop? | TRUE | app/agent/llm_client.py, app/agent/loop.py | app/agent/llm_client.py, app/agent/loop.py | TRUE |
| `gs_agent_005` | What happens if an individual tool execution fails during the agent loop? | What happens if an individual tool execution fails during the agent loop? | TRUE | app/agent/loop.py, app/agent/tools.py | app/agent/loop.py, app/agent/tools.py | TRUE |
| `gs_api_001` | How is rate limiting implemented on the API endpoints? | How is rate limiting implemented on the API endpoints? | TRUE | app/api/rate_limiter.py, app/main.py | app/api/rate_limiter.py, app/main.py | TRUE |
| `gs_api_002` | What validation does the /chat endpoint perform on the user question? | What validation does the /chat endpoint perform on the user question? | TRUE | app/api/router.py | app/api/router.py | TRUE |
| `gs_api_003` | How does the API handle an unhandled exception globally? | How does the API handle an unhandled exception globally? | TRUE | app/main.py | app/main.py | TRUE |
| `gs_api_004` | Is the /ingest endpoint synchronous or asynchronous? | Is the /ingest endpoint synchronous or asynchronous? | TRUE | app/api/router.py | app/api/router.py | TRUE |
| `gs_api_005` | What is the return structure of the /eval/status endpoint? | What is the return structure of the /eval/status endpoint? | TRUE | app/api/router.py | app/api/router.py | TRUE |
| `gs_graph_001` | How does the graph builder detect circular dependencies? | How does the graph builder detect circular dependencies? | TRUE | app/graph/builder.py | app/graph/builder.py | TRUE |
| `gs_graph_002` | What is the maximum number of nodes allowed in the graph? | What is the maximum number of nodes allowed in the graph? | TRUE | app/config.py, app/graph/builder.py | app/config.py, app/graph/builder.py | TRUE |
| `gs_graph_003` | How does get_subgraph limit the depth of the returned graph? | How does get_subgraph limit the depth of the returned graph? | TRUE | app/graph/queries.py | app/graph/queries.py | TRUE |
| `gs_graph_004` | What format is the graph converted to for visualization? | What format is the graph converted to for visualization? | TRUE | app/diagrams/mermaid.py, app/graph/queries.py | app/diagrams/mermaid.py, app/graph/queries.py | TRUE |
| `gs_graph_005` | Are class methods linked to their parent classes in the call graph? | Are class methods linked to their parent classes in the call graph? | TRUE | app/graph/builder.py | app/graph/builder.py | TRUE |
| `gs_hall_001` | Is the class InvalidUrlException defined in app/api/router.py? | Is the class InvalidUrlException defined in app/api/router.py? | TRUE |  |  | TRUE |
| `gs_hall_002` | Does app/graph/builder.py define a CypherQueryExecutor class? | Does app/graph/builder.py define a CypherQueryExecutor class? | TRUE |  |  | TRUE |
| `gs_ingest_001` | How does the ingestion pipeline handle large repositories? | How does the ingestion pipeline handle large repositories? | TRUE | app/config.py, app/ingestion/clone.py | app/config.py, app/ingestion/clone.py | TRUE |
| `gs_ingest_002` | What happens if the GitHub webhook receives a push event on a non-default branch? | What happens if the GitHub webhook receives a push event on a non-default branch? | TRUE | app/webhook/github_webhook.py | app/webhook/github_webhook.py | TRUE |
| `gs_ingest_003` | Which file extensions are allowed during the chunking phase? | Which file extensions are allowed during the chunking phase? | TRUE | app/config.py, app/ingestion/chunker.py | app/config.py, app/ingestion/chunker.py | TRUE |
| `gs_ingest_004` | How is the ingestion lock implemented to prevent concurrent ingestion of the same repo? | How is the ingestion lock implemented to prevent concurrent ingestion of the same repo? | TRUE | app/api/router.py, app/ingestion/metadata_store.py | app/api/router.py, app/ingestion/metadata_store.py | TRUE |
| `gs_ingest_005` | What is the role of metadata_store.mark_synced? | What is the role of metadata_store.mark_synced? | TRUE | app/ingestion/metadata_store.py | app/ingestion/metadata_store.py | TRUE |
| `gs_retrieval_001` | How does hybrid search combine BM25 and vector scores? | How does hybrid search combine BM25 and vector scores? | TRUE | app/retrieval/hybrid_search.py | app/retrieval/hybrid_search.py | TRUE |
| `gs_retrieval_002` | Where is the BM25 index persisted on disk? | Where is the BM25 index persisted on disk? | TRUE | app/retrieval/bm25_store.py | app/retrieval/bm25_store.py | TRUE |
| `gs_retrieval_003` | Does the pipeline use a cross-encoder reranker? | Does the pipeline use a cross-encoder reranker? | TRUE | app/retrieval/hybrid_search.py, app/retrieval/reranker.py | app/retrieval/hybrid_search.py, app/retrieval/reranker.py | TRUE |
| `gs_retrieval_004` | What happens if query expansion LLM request times out? | What happens if query expansion LLM request times out? | TRUE | app/retrieval/query_expansion.py | app/retrieval/query_expansion.py | TRUE |
| `gs_retrieval_005` | What vector database is used for semantic search? | What vector database is used for semantic search? | TRUE | app/chroma_client.py, app/retrieval/vector_store.py | app/chroma_client.py, app/retrieval/vector_store.py | TRUE |

## 7. Exact High-Risk Query Comparison

| query_id | EXP-A Question Text | EXP-B Question Text | Match? |
| --- | --- | --- | :---: |
| `gs_agent_001` | How does the agent avoid executing duplicate tool calls? | How does the agent avoid executing duplicate tool calls? | TRUE |
| `gs_agent_002` | What determines if an agent's answer is 'gated' due to hallucination? | What determines if an agent's answer is 'gated' due to hallucination? | TRUE |
| `gs_agent_003` | How long is a semantic cache entry valid? | How long is a semantic cache entry valid? | TRUE |
| `gs_agent_004` | How are LLM rate limits handled in the agent loop? | How are LLM rate limits handled in the agent loop? | TRUE |
| `gs_agent_005` | What happens if an individual tool execution fails during the agent loop? | What happens if an individual tool execution fails during the agent loop? | TRUE |
| `gs_api_001` | How is rate limiting implemented on the API endpoints? | How is rate limiting implemented on the API endpoints? | TRUE |
| `gs_api_003` | How does the API handle an unhandled exception globally? | How does the API handle an unhandled exception globally? | TRUE |

## 8. Ground-Truth Comparison

All 27 ground-truth file mappings are **100% identical** between EXP-A and EXP-B raw outputs.

## 9. Raw Output Consistency Check

Both `exp_a_full_system_live.json` and `exp_b_naive_dense_rag_live.json` contain exactly 27 records in identical query ID sequence (`gs_ingest_001` through `gs_hall_002`). Question text embedded in raw output records matches the runner script definitions verbatim.

## 10. Benchmark Hash Analysis

Calculating SHA-256 on `json.dumps(BENCHMARK_QUERIES, indent=2).encode('utf-8')` yields `5afb58a9ff44e2b9d4b5c10c06cb2ff6747a5882b3cf61b1923feb13f95c1ccd`. This matches the recorded `benchmark_hash` field in experiment config manifests.

## 11. Git Provenance

* `data/golden_set.json` is tracked in git.
* `experiments/live/full_system_exp_a.py` is tracked in git.
* `experiments/live/naive_dense_baseline.py` is tracked in git.

## 12. Duplicate / Stale Benchmark Detection

No active script loads an outdated or conflicting query array during execution. Both runner scripts contain identical `BENCHMARK_QUERIES` arrays.

## 13. Previous Audit Contradictions

No contradictions found between raw filesystem evidence and claims of benchmark identity. The raw files on disk confirm 27/27 identical query inputs.

## 14. Evidence Classification

**VERIFIED** — Primary filesystem evidence establishes that both experiments consumed identical inputs.

## 15. Final Paired-Comparison Verdict

### **A — VALID PAIRED BENCHMARK**

## 16. Paper Methodology Consequence

EXP-A vs EXP-B can legitimately be treated as a controlled, paired experimental comparison on the 27-query benchmark.

## 17. Reproducibility Recommendations

Consolidate the 27-query array into a single static JSON file `experiments/live/benchmark_27.json` on disk to ensure single-source-of-truth loading across future evaluation runs.
