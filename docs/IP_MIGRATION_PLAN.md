# CodeNavigator — Intellectual Property Migration Plan

To protect the unique competitive advantages of the CodeNavigator project while keeping a clean public-facing repository for portfolio demonstration, it is recommended to extract the proprietary reasoning, prompt templates, reranking logic, and evaluation metrics into a separate private repository. 

This document outlines the step-by-step migration architecture.

---

## 1. Proprietary Modules Identified for Isolation

| Component | Path | Description | IP Classification |
|---|---|---|---|
| **AI Agent Loop** | `app/agent/loop.py` | Core iterative LLM execution engine and tool dispatcher | High |
| **Prompt Engineering** | `app/agent/system_prompt.py` | System-level prompt guidelines, role directives, and formatting instructions | High |
| **Confidence Guard** | `app/agent/confidence.py` | Hallucination prevention and citation checking algorithm | High |
| **Hybrid Search & RRF** | `app/retrieval/hybrid_search.py` | Reciprocal Rank Fusion blending logic | Medium |
| **Cross-Encoder Reranker** | `app/retrieval/reranker.py` | MS-Marco MiniLM reranking implementation | Medium |
| **Semantic Cache** | `app/agent/semantic_cache.py` | Query-matching caching with similarity thresholds | Medium |
| **Ragas Eval Suite** | `eval/` & `app/evaluation/` | Automated scoring models, golden sets, and regression tests | Medium |

---

## 2. Target Hybrid Architecture

Instead of having all code in one public repository, the system can split into a **Public Interface Wrapper** and a **Private Core Package**:

```
[Public Portfolio Repo: CodeNavigator]
  └── app/
      ├── main.py (Public API router)
      ├── ingestion/ (Standard Git cloning & parsing)
      └── agent/
          └── loop_stub.py <─── (Standard HTTP/GRPC Client to Private API)
                                      |
                                      v  [Secure API Call]
[Private Logic Service: CodeNavigator-Core]   |
  ├── app/agent/loop.py <─────────────────────┘
  ├── app/agent/system_prompt.py
  └── app/agent/confidence.py
```

---

## 3. Migration Execution Steps

### Step 1: Initialize Private Core Repository
1. Create a new private repository: `codenavigator-core`.
2. Extract the `app/agent/`, `app/retrieval/` (specifically `hybrid_search.py` and `reranker.py`), and `eval/` directories into the private repository.
3. Package it using `pyproject.toml` or `setup.py` as a private pip package (`codenavigator_core`).

### Step 2: Implement Dependency Injection Stubs
In the public `CodeNavigator` repository, replace the heavy logic files with clean interface stubs:
- For example, in `app/agent/loop.py`:
  ```python
  # Stub for Public Repository
  # Replaces full agent loop logic with a client request to the private Core backend
  import httpx
  from app.config import settings

  async def run_agent_loop(question: str, repo_id: str):
      async with httpx.AsyncClient() as client:
          response = await client.post(
              f"{settings.PRIVATE_CORE_URL}/agent/run",
              json={"question": question, "repo_id": repo_id},
              headers={"X-Internal-Key": settings.INTERNAL_SECRET}
          )
          return response.json()
  ```

### Step 3: Deployment Isolation
1. Deploy the `codenavigator-core` service privately (e.g., inside a private VPC, behind an AWS API Gateway, or as a private Render Web Service).
2. Point the public Streamlit/FastAPI web interface to the private service's URL using environment variables.

---

## 4. Benefits of Migration
- **Protects Secret Prompts:** Prevents competitors or bots from scraping your heavily-engineered system prompts.
- **Shows Clean Architecture:** Recruiters can still see your API endpoints, file structures, database interactions, and clean integration patterns while appreciating your focus on code security.
- **Minimizes Attack Surface:** Reduces the code exposed to security vulnerability scans.
