#!/usr/bin/env python3
"""
experiments/live/full_system_exp_a.py
--------------------------------------
GENUINE LIVE FULL CODENAVIGATOR SYSTEM EXPERIMENT (EXP-A)

Execution Pipeline:
1. Loads 27 Golden Set benchmark queries.
2. Executes full agent loop via app.agent.loop.run(repo_id, question).
   - Dense vector + BM25 sparse search + RRF fusion
   - Cross-Encoder reranking
   - Call graph traversal & symbol resolution
   - Multi-step FSM agent reasoning & tool dispatch
   - Grounding check, confidence scoring & verification gating
3. Captures raw model answer, cited sources, confidence score, gated flag, latency, and retrieval hits verbatim.
4. Saves complete raw JSON output to experiments/live/raw/exp_a_full_system_live.json.
"""

import os
import sys
import time
import json
import hashlib
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.agent.loop import run as run_agent_loop, ProviderError

BENCHMARK_QUERIES = [
    {"id": "gs_ingest_001", "category": "ingestion", "question": "How does the ingestion pipeline handle large repositories?", "ground_truth_files": ["app/ingestion/clone.py", "app/config.py"]},
    {"id": "gs_ingest_002", "category": "ingestion", "question": "What happens if the GitHub webhook receives a push event on a non-default branch?", "ground_truth_files": ["app/webhook/github_webhook.py"]},
    {"id": "gs_ingest_003", "category": "ingestion", "question": "Which file extensions are allowed during the chunking phase?", "ground_truth_files": ["app/ingestion/chunker.py", "app/config.py"]},
    {"id": "gs_ingest_004", "category": "ingestion", "question": "How is the ingestion lock implemented to prevent concurrent ingestion of the same repo?", "ground_truth_files": ["app/ingestion/metadata_store.py", "app/api/router.py"]},
    {"id": "gs_ingest_005", "category": "ingestion", "question": "What is the role of metadata_store.mark_synced?", "ground_truth_files": ["app/ingestion/metadata_store.py"]},
    {"id": "gs_retrieval_001", "category": "retrieval", "question": "How does hybrid search combine BM25 and vector scores?", "ground_truth_files": ["app/retrieval/hybrid_search.py"]},
    {"id": "gs_retrieval_002", "category": "retrieval", "question": "Where is the BM25 index persisted on disk?", "ground_truth_files": ["app/retrieval/bm25_store.py"]},
    {"id": "gs_retrieval_003", "category": "retrieval", "question": "Does the pipeline use a cross-encoder reranker?", "ground_truth_files": ["app/retrieval/hybrid_search.py", "app/retrieval/reranker.py"]},
    {"id": "gs_retrieval_004", "category": "retrieval", "question": "What happens if query expansion LLM request times out?", "ground_truth_files": ["app/retrieval/query_expansion.py"]},
    {"id": "gs_retrieval_005", "category": "retrieval", "question": "What vector database is used for semantic search?", "ground_truth_files": ["app/retrieval/vector_store.py", "app/chroma_client.py"]},
    {"id": "gs_agent_001", "category": "agent", "question": "How does the agent avoid executing duplicate tool calls?", "ground_truth_files": ["app/agent/loop.py", "app/agent/tools.py"]},
    {"id": "gs_agent_002", "category": "agent", "question": "What determines if an agent's answer is 'gated' due to hallucination?", "ground_truth_files": ["app/agent/loop.py", "app/agent/confidence.py", "app/agent/claim_verification.py"]},
    {"id": "gs_agent_003", "category": "agent", "question": "How long is a semantic cache entry valid?", "ground_truth_files": ["app/agent/semantic_cache.py", "app/config.py"]},
    {"id": "gs_agent_004", "category": "agent", "question": "How are LLM rate limits handled in the agent loop?", "ground_truth_files": ["app/agent/loop.py", "app/agent/llm_client.py"]},
    {"id": "gs_agent_005", "category": "agent", "question": "What happens if an individual tool execution fails during the agent loop?", "ground_truth_files": ["app/agent/loop.py", "app/agent/tools.py"]},
    {"id": "gs_graph_001", "category": "graph", "question": "How does the graph builder detect circular dependencies?", "ground_truth_files": ["app/graph/builder.py"]},
    {"id": "gs_graph_002", "category": "graph", "question": "What is the maximum number of nodes allowed in the graph?", "ground_truth_files": ["app/graph/builder.py", "app/config.py"]},
    {"id": "gs_graph_003", "category": "graph", "question": "How does get_subgraph limit the depth of the returned graph?", "ground_truth_files": ["app/graph/queries.py"]},
    {"id": "gs_graph_004", "category": "graph", "question": "What format is the graph converted to for visualization?", "ground_truth_files": ["app/diagrams/mermaid.py", "app/graph/queries.py"]},
    {"id": "gs_graph_005", "category": "graph", "question": "Are class methods linked to their parent classes in the call graph?", "ground_truth_files": ["app/graph/builder.py"]},
    {"id": "gs_api_001", "category": "api", "question": "How is rate limiting implemented on the API endpoints?", "ground_truth_files": ["app/api/rate_limiter.py", "app/main.py"]},
    {"id": "gs_api_002", "category": "api", "question": "What validation does the /chat endpoint perform on the user question?", "ground_truth_files": ["app/api/router.py"]},
    {"id": "gs_api_003", "category": "api", "question": "How does the API handle an unhandled exception globally?", "ground_truth_files": ["app/main.py"]},
    {"id": "gs_api_004", "category": "api", "question": "Is the /ingest endpoint synchronous or asynchronous?", "ground_truth_files": ["app/api/router.py"]},
    {"id": "gs_api_005", "category": "api", "question": "What is the return structure of the /eval/status endpoint?", "ground_truth_files": ["app/api/router.py"]},
    {"id": "gs_hall_001", "category": "hallucination", "question": "Is the class InvalidUrlException defined in app/api/router.py?", "ground_truth_files": []},
    {"id": "gs_hall_002", "category": "hallucination", "question": "Does app/graph/builder.py define a CypherQueryExecutor class?", "ground_truth_files": []}
]

def main():
    print("=== STARTING LIVE FULL SYSTEM EXP-A EXPERIMENT ===")
    
    config_dir = PROJECT_ROOT / "experiments" / "live" / "config"
    out_dir = PROJECT_ROOT / "experiments" / "live" / "raw"
    config_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "exp_a_full_system_live.json"
    config_path = config_dir / "exp_a_live_config.json"

    repo_id = "5749924cb6a9850057686b664b4b980fc407af109104df6f0aec8ec8182a4338"

    benchmark_bytes = json.dumps(BENCHMARK_QUERIES, indent=2).encode("utf-8")
    benchmark_hash = hashlib.sha256(benchmark_bytes).hexdigest()

    config_manifest = {
        "experiment_id": "EXP-A_LIVE",
        "experiment_name": "Full CodeNavigator System Live Rerun",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository_id": repo_id,
        "benchmark_hash": benchmark_hash,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "dense_enabled": True,
        "bm25_enabled": True,
        "rrf_enabled": True,
        "reranker_enabled": getattr(settings, "ENABLE_RERANKER", True),
        "graph_enabled": True,
        "agent_enabled": True,
        "semantic_cache_enabled": settings.SEMANTIC_CACHE_ENABLED,
        "query_expansion_enabled": getattr(settings, "QUERY_EXPANSION_ENABLED", False),
        "verification_enabled": True,
        "confidence_gate_enabled": True,
        "top_k": 10,
        "reranker_top_k": 5,
        "graph_depth": 3,
        "confidence_threshold": getattr(settings, "MIN_CONFIDENCE_SCORE", 4.0)
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_manifest, f, indent=2)

    print(f"Config Manifest Saved To: {config_path}")
    print(f"Benchmark Hash (SHA-256): {benchmark_hash}")
    print(f"LLM Model: {settings.LLM_MODEL}")
    print(f"Target Repo ID: {repo_id}")
    print(f"Total Benchmark Queries: {len(BENCHMARK_QUERIES)}\n")

    results = []

    for i, item in enumerate(BENCHMARK_QUERIES, 1):
        qid = item["id"]
        cat = item["category"]
        question = item["question"]
        gt_files = item["ground_truth_files"]

        print(f"[{i:02d}/{len(BENCHMARK_QUERIES)}] Query {qid} ({cat}): '{question}'")

        start_time = time.monotonic()
        error_msg = None
        agent_res = {}

        max_retries = 5
        for retry in range(max_retries):
            try:
                agent_res = run_agent_loop(repo_id=repo_id, question=question)
                if agent_res.get("rate_limited") and retry < max_retries - 1:
                    sleep_s = agent_res.get("retry_after_s", 15.0)
                    print(f"  [RATE LIMIT] Sleeping {sleep_s}s before retry {retry+1}/{max_retries}...")
                    time.sleep(sleep_s)
                    continue
                break
            except ProviderError as pe:
                if "rate limit" in str(pe).lower() and retry < max_retries - 1:
                    sleep_s = 15.0 * (retry + 1)
                    print(f"  [RATE LIMIT EXCEPTION] Sleeping {sleep_s}s before retry {retry+1}/{max_retries}...")
                    time.sleep(sleep_s)
                else:
                    error_msg = str(pe)
                    break
            except Exception as e:
                error_msg = str(e)
                break

        elapsed_s = round(time.monotonic() - start_time, 2)

        sources = agent_res.get("sources", [])
        cited_files = []
        for s in sources:
            fp = s.get("file_path") or s.get("display_path") or ""
            if fp and fp not in cited_files:
                cited_files.append(fp)

        print(f"  Done in {elapsed_s}s. Gated: {agent_res.get('gated', False)}, Confidence: {agent_res.get('confidence_score', 0.0)}, Sources: {len(cited_files)}")

        record = {
            "query_id": qid,
            "category": cat,
            "question": question,
            "ground_truth_files": gt_files,
            "model_answer": agent_res.get("answer", ""),
            "cited_files": cited_files,
            "sources": sources,
            "confidence_score": agent_res.get("confidence_score", 0.0),
            "gated": agent_res.get("gated", False),
            "retrieved_hits": agent_res.get("retrieval_hits", []),
            "timing": agent_res.get("timing", {}),
            "groq_calls": agent_res.get("groq_calls", 0),
            "latency_s": elapsed_s,
            "error": error_msg or agent_res.get("error")
        }
        results.append(record)
        time.sleep(5.0)

    output_artifact = {
        "experiment_id": "EXP-A_LIVE",
        "experiment_name": "Full CodeNavigator System Live Rerun",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "configuration": config_manifest,
        "total_queries": len(results),
        "results": results
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_artifact, f, indent=2)

    print(f"\n=== EXPERIMENT COMPLETE. SAVED RAW OUTPUT TO {out_path} ===")

if __name__ == "__main__":
    main()
