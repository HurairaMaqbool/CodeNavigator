#!/usr/bin/env python3
"""
experiments/live/naive_dense_baseline.py
-----------------------------------------
GENUINE LIVE NAIVE DENSE RAG BASELINE EXPERIMENT

Execution Pipeline:
1. Loads 27 Golden Set benchmark queries.
2. Queries ChromaDB vector store directly using dense embeddings (top_k=5).
   - Skips BM25 sparse search
   - Skips Reciprocal Rank Fusion (RRF)
   - Skips Cross-Encoder Reranking
   - Skips NetworkX Call Graph Traversal
   - Skips Verification Gating / Intent Firewall
3. Sends retrieved chunks + question directly to Groq LLM (qwen/qwen3.6-27b).
4. Captures model answer, cited files, latency, and retrieved chunk metadata verbatim.
5. Saves complete raw JSON output to experiments/live/exp_b_naive_dense_rag_live.json.
"""

import os
import sys
import time
import json
import re
from pathlib import Path

# Set UTF-8 encoding for standard output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.retrieval.embeddings import embed
from app.retrieval.vector_store import query as chroma_vector_query
from app.agent.llm_client import get_llm_client, ProviderError

# Benchmark Questions Mapping
BENCHMARK_QUERIES = [
    {
        "id": "gs_ingest_001",
        "category": "ingestion",
        "question": "How does the ingestion pipeline handle large repositories?",
        "ground_truth_files": ["app/ingestion/clone.py", "app/config.py"]
    },
    {
        "id": "gs_ingest_002",
        "category": "ingestion",
        "question": "What happens if the GitHub webhook receives a push event on a non-default branch?",
        "ground_truth_files": ["app/webhook/github_webhook.py"]
    },
    {
        "id": "gs_ingest_003",
        "category": "ingestion",
        "question": "Which file extensions are allowed during the chunking phase?",
        "ground_truth_files": ["app/ingestion/chunker.py", "app/config.py"]
    },
    {
        "id": "gs_ingest_004",
        "category": "ingestion",
        "question": "How is the ingestion lock implemented to prevent concurrent ingestion of the same repo?",
        "ground_truth_files": ["app/ingestion/metadata_store.py", "app/api/router.py"]
    },
    {
        "id": "gs_ingest_005",
        "category": "ingestion",
        "question": "What is the role of metadata_store.mark_synced?",
        "ground_truth_files": ["app/ingestion/metadata_store.py"]
    },
    {
        "id": "gs_retrieval_001",
        "category": "retrieval",
        "question": "How does hybrid search combine BM25 and vector scores?",
        "ground_truth_files": ["app/retrieval/hybrid_search.py"]
    },
    {
        "id": "gs_retrieval_002",
        "category": "retrieval",
        "question": "Where is the BM25 index persisted on disk?",
        "ground_truth_files": ["app/retrieval/bm25_store.py"]
    },
    {
        "id": "gs_retrieval_003",
        "category": "retrieval",
        "question": "Does the pipeline use a cross-encoder reranker?",
        "ground_truth_files": ["app/retrieval/hybrid_search.py", "app/retrieval/reranker.py"]
    },
    {
        "id": "gs_retrieval_004",
        "category": "retrieval",
        "question": "What happens if query expansion LLM request times out?",
        "ground_truth_files": ["app/retrieval/query_expansion.py"]
    },
    {
        "id": "gs_retrieval_005",
        "category": "retrieval",
        "question": "What vector database is used for semantic search?",
        "ground_truth_files": ["app/retrieval/vector_store.py", "app/chroma_client.py"]
    },
    {
        "id": "gs_agent_001",
        "category": "agent",
        "question": "How does the agent avoid executing duplicate tool calls?",
        "ground_truth_files": ["app/agent/loop.py", "app/agent/tools.py"]
    },
    {
        "id": "gs_agent_002",
        "category": "agent",
        "question": "What determines if an agent's answer is 'gated' due to hallucination?",
        "ground_truth_files": ["app/agent/loop.py", "app/agent/confidence.py", "app/agent/claim_verification.py"]
    },
    {
        "id": "gs_agent_003",
        "category": "agent",
        "question": "How long is a semantic cache entry valid?",
        "ground_truth_files": ["app/agent/semantic_cache.py", "app/config.py"]
    },
    {
        "id": "gs_agent_004",
        "category": "agent",
        "question": "How are LLM rate limits handled in the agent loop?",
        "ground_truth_files": ["app/agent/loop.py", "app/agent/llm_client.py"]
    },
    {
        "id": "gs_agent_005",
        "category": "agent",
        "question": "What happens if an individual tool execution fails during the agent loop?",
        "ground_truth_files": ["app/agent/loop.py", "app/agent/tools.py"]
    },
    {
        "id": "gs_graph_001",
        "category": "graph",
        "question": "How does the graph builder detect circular dependencies?",
        "ground_truth_files": ["app/graph/builder.py"]
    },
    {
        "id": "gs_graph_002",
        "category": "graph",
        "question": "What is the maximum number of nodes allowed in the graph?",
        "ground_truth_files": ["app/graph/builder.py", "app/config.py"]
    },
    {
        "id": "gs_graph_003",
        "category": "graph",
        "question": "How does get_subgraph limit the depth of the returned graph?",
        "ground_truth_files": ["app/graph/queries.py"]
    },
    {
        "id": "gs_graph_004",
        "category": "graph",
        "question": "What format is the graph converted to for visualization?",
        "ground_truth_files": ["app/diagrams/mermaid.py", "app/graph/queries.py"]
    },
    {
        "id": "gs_graph_005",
        "category": "graph",
        "question": "Are class methods linked to their parent classes in the call graph?",
        "ground_truth_files": ["app/graph/builder.py"]
    },
    {
        "id": "gs_api_001",
        "category": "api",
        "question": "How is rate limiting implemented on the API endpoints?",
        "ground_truth_files": ["app/api/rate_limiter.py", "app/main.py"]
    },
    {
        "id": "gs_api_002",
        "category": "api",
        "question": "What validation does the /chat endpoint perform on the user question?",
        "ground_truth_files": ["app/api/router.py"]
    },
    {
        "id": "gs_api_003",
        "category": "api",
        "question": "How does the API handle an unhandled exception globally?",
        "ground_truth_files": ["app/main.py"]
    },
    {
        "id": "gs_api_004",
        "category": "api",
        "question": "Is the /ingest endpoint synchronous or asynchronous?",
        "ground_truth_files": ["app/api/router.py"]
    },
    {
        "id": "gs_api_005",
        "category": "api",
        "question": "What is the return structure of the /eval/status endpoint?",
        "ground_truth_files": ["app/api/router.py"]
    },
    {
        "id": "gs_hall_001",
        "category": "hallucination",
        "question": "Is the class InvalidUrlException defined in app/api/router.py?",
        "ground_truth_files": []
    },
    {
        "id": "gs_hall_002",
        "category": "hallucination",
        "question": "Does app/graph/builder.py define a CypherQueryExecutor class?",
        "ground_truth_files": []
    }
]

def extract_citations(text: str) -> list[str]:
    """Extract cited file paths from response text (matches file_path:start-end or file_path)."""
    pattern = r'`?([a-zA-Z0-9_\-\/]+\.py)(?::\d+-\d+)?`?'
    matches = re.findall(pattern, text)
    unique_files = list(dict.fromkeys(matches))
    return unique_files

def parse_llm_response_text(res_obj) -> str:
    """Parse string output from LLMResponse object content."""
    content = getattr(res_obj, "content", res_obj)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)

def main():
    print("=== STARTING LIVE NAIVE DENSE RAG BASELINE EXPERIMENT ===")
    out_dir = PROJECT_ROOT / "experiments" / "live" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "exp_b_naive_dense_rag_live.json"

    # Default codebase repo ID in ChromaDB
    repo_id = "5749924cb6a9850057686b664b4b980fc407af109104df6f0aec8ec8182a4338"

    llm_client = get_llm_client()
    print(f"LLM Client Initialized: {llm_client.__class__.__name__}")
    print(f"LLM Model: {settings.LLM_MODEL}")
    print(f"Embedding Model: {settings.EMBEDDING_MODEL}")
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
        answer_text = ""
        cited_files = []
        retrieved_chunks_summary = []

        try:
            # Step 1: Embed question using sentence-transformers (all-MiniLM-L6-v2)
            q_vector = embed(question)

            # Step 2: Dense Vector Retrieval in ChromaDB (top_k=5)
            hits = chroma_vector_query(repo_id, q_vector, top_k=5)

            # Format context string
            context_blocks = []
            for h in hits:
                meta = h.get("chunk_metadata", {})
                file_path = meta.get("display_path") or meta.get("file_path") or "unknown"
                start_line = meta.get("start_line", 1)
                end_line = meta.get("end_line", 1)
                text = h.get("chunk", "")
                context_blocks.append(f"--- File: {file_path}:{start_line}-{end_line} ---\n{text}")
                retrieved_chunks_summary.append({
                    "file_path": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "score": round(float(h.get("score", 0.0)), 4)
                })

            context_str = "\n\n".join(context_blocks)

            # Step 3: Send directly to Groq LLM with retries on rate limits
            sys_prompt = (
                "You are an expert AI software engineer. Answer the user's question using ONLY the provided code context. "
                "Cite specific source files in markdown format `file_path:start_line-end_line`. "
                "If the context does not contain enough information to answer, state clearly that the reference cannot be verified."
            )
            user_prompt = f"Code Context:\n{context_str}\n\nUser Question: {question}"

            response_obj = None
            max_retries = 6
            for retry in range(max_retries):
                try:
                    response_obj = llm_client.create(
                        system=sys_prompt,
                        messages=[{"role": "user", "content": user_prompt}],
                        max_tokens=250
                    )
                    break
                except Exception as exc:
                    if "rate limit" in str(exc).lower() and retry < max_retries - 1:
                        sleep_time = 12.0 * (retry + 1)
                        print(f"  [RATE LIMIT] Sleeping {sleep_time}s before retry {retry+1}/{max_retries}...")
                        time.sleep(sleep_time)
                    else:
                        raise exc

            answer_text = parse_llm_response_text(response_obj)
            cited_files = extract_citations(answer_text)

        except ProviderError as pe:
            error_msg = f"ProviderError: {pe}"
            answer_text = f"LLM Inference Error: {pe}"
            print(f"  [ERROR] {error_msg}")
        except Exception as e:
            error_msg = f"Unexpected Exception: {e}"
            answer_text = f"Execution Error: {e}"
            print(f"  [ERROR] {error_msg}")

        elapsed_s = round(time.monotonic() - start_time, 2)
        print(f"  Done in {elapsed_s}s. Cited files: {cited_files}")

        record = {
            "query_id": qid,
            "category": cat,
            "question": question,
            "ground_truth_files": gt_files,
            "retrieved_chunks": retrieved_chunks_summary,
            "model_answer": answer_text,
            "cited_files": cited_files,
            "latency_s": elapsed_s,
            "error": error_msg
        }
        results.append(record)
        # Sleep 5.0s between requests to respect Groq OTPM rate limit
        time.sleep(5.0)

    # Save Output JSON
    output_artifact = {
        "experiment_id": "EXP-B_LIVE",
        "experiment_name": "Naive Dense RAG Live Baseline",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "configuration": {
            "repo_id": repo_id,
            "embedding_model": settings.EMBEDDING_MODEL,
            "llm_model": settings.LLM_MODEL,
            "llm_provider": settings.LLM_PROVIDER,
            "top_k": 5,
            "bm25_enabled": False,
            "rrf_enabled": False,
            "reranker_enabled": False,
            "graph_enabled": False,
            "verification_gating_enabled": False
        },
        "total_queries": len(results),
        "results": results
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_artifact, f, indent=2)

    print(f"\n=== EXPERIMENT COMPLETE. SAVED RAW OUTPUT TO {out_path} ===")

if __name__ == "__main__":
    main()
