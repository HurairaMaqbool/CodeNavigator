<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=220&section=header&text=🧠%20Codebase%20Onboarding%20Agent&fontSize=42&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Agentic%20Graph-Augmented%20RAG%20Pipeline%20for%20Codebase%20Intelligence&descSize=15&descAlignY=58&descColor=a0a0cc" width="100%"/>

<br/>

[![Stars](https://img.shields.io/github/stars/HurairaMaqbool/HurairaMaqbool?style=for-the-badge&logo=github&color=FFD700&labelColor=0d1117)](https://github.com/HurairaMaqbool/HurairaMaqbool/stargazers)
[![Forks](https://img.shields.io/github/forks/HurairaMaqbool/HurairaMaqbool?style=for-the-badge&logo=git&color=4ECDC4&labelColor=0d1117)](https://github.com/HurairaMaqbool/HurairaMaqbool/network)
[![Issues](https://img.shields.io/github/issues/HurairaMaqbool/HurairaMaqbool?style=for-the-badge&logo=gitbook&color=FF6B6B&labelColor=0d1117)](https://github.com/HurairaMaqbool/HurairaMaqbool/issues)
[![License](https://img.shields.io/badge/License-MIT-8A2BE2?style=for-the-badge&labelColor=0d1117)](LICENSE)

<br/>

![Python](https://img.shields.io/badge/Python%203.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=next.js&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorStore-6E57F7?style=flat-square)
![NetworkX](https://img.shields.io/badge/NetworkX-GraphEngine-orange?style=flat-square)
![LangChain](https://img.shields.io/badge/LangChain-Agentic-1C3C3C?style=flat-square)
![Groq](https://img.shields.io/badge/Groq-LLM-F55036?style=flat-square)

<br/>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=18&pause=1000&color=6E57F7&center=true&vCenter=true&width=650&lines=Ask+any+question+about+your+codebase.;Hybrid+RAG+%2B+Graph+traversal+%2B+Hallucination+gating.;Auto-syncs+on+every+GitHub+push.;Built+for+developers%2C+not+demos." alt="Typing SVG"/>

<br/><br/>

</div>

---

<details open>
<summary><b>📋 Table of Contents</b> — click to expand / collapse</summary>

<br/>

| # | Section |
|---|---------|
| 1 | [🧠 About the Project](#-about-the-project) |
| 2 | [✨ Features at a Glance](#-features-at-a-glance) |
| 3 | [🏗️ High-Level Architecture](#️-high-level-architecture) |
| 4 | [⚙️ Workflow Breakdowns](#️-workflow-breakdowns) |
| 5 | [📦 Module Reference](#-module-reference) |
| 6 | [🔌 API Contracts](#-api-contracts) |
| 7 | [🛡️ Agentic Gating & Hallucination Guard](#️-agentic-gating--hallucination-guard) |
| 8 | [🛠️ Tech Stack](#️-tech-stack) |
| 9 | [📁 Project Structure](#-project-structure) |
| 10 | [🚀 Setup & Local Execution](#-setup--local-execution) |
| 11 | [🧪 Testing](#-testing) |
| 12 | [🛣️ Roadmap](#️-roadmap) |
| 13 | [🤝 Contributing](#-contributing) |
| 14 | [📄 License](#-license) |
| 15 | [👤 Author](#-author) |

</details>

---

## 🧠 About the Project

<img align="right" src="https://user-images.githubusercontent.com/79131292/144742785-d183f50a-52d6-4296-a43a-90a1ee3502d8.png" width="35%"/>

**Onboarding onto a new codebase takes days — sometimes weeks.** Developers waste hours tracing function calls, reading stale docs, and asking colleagues questions that interrupt everyone's flow.

The **Codebase Onboarding Agent** eliminates that friction. It ingests any Git repository, builds a triple index (semantic vectors + BM25 keyword + call graph), and exposes an autonomous RAG agent that answers precise, citation-verified questions about the codebase in seconds.

This is not a chatbot wrapper around an LLM. It is a production-grade agentic pipeline with:

- 🔬 **AST-level chunking** — logic is never split mid-function
- 🕸️ **Graph-augmented retrieval** — understand *who calls what*
- 🛡️ **Hallucination gating** — every citation is verified against the index before it reaches the user
- ⚡ **Semantic answer caching** — repeat questions are served in milliseconds
- 🔄 **Webhook auto-sync** — the agent updates itself on every GitHub push

<br clear="right"/>

### The core problem

| Old Way | This Agent |
|---------|-----------|
| Read docs that may be stale | Answers from the actual, live code |
| Grep and trace calls manually | Graph traversal finds callers/callees instantly |
| Ask a senior dev (interrupt their flow) | Ask the agent — it cites the exact file and line |
| Re-onboard after every big PR | Webhook re-ingests on merge, cache is purged |

---

## ✨ Features at a Glance

<div align="center">

| | Feature | Description |
|-|---------|-------------|
| 🤖 | **Autonomous Agent Loop** | LLM decides which tools to call — no hardcoded router |
| 🔍 | **Hybrid Search** | Vector (ChromaDB) + Keyword (BM25) fused via Reciprocal Rank Fusion |
| 🕸️ | **Call Graph Engine** | NetworkX graph of imports and function calls — traversed via BFS (3-hop limit) |
| 🛡️ | **Hallucination Guard** | Citation validation gates any response with confidence < 4.0 / 10 |
| ⚡ | **Semantic Cache** | 95% similarity threshold — identical questions skip the LLM entirely |
| 📊 | **Mermaid Diagrams** | Auto-generates call-graph diagrams in the Next.js UI |
| 🔄 | **Webhook Auto-Sync** | HMAC-verified GitHub webhooks trigger re-ingestion on every push |
| 🌐 | **REST API** | FastAPI backend with X-API-Key auth and sliding-window rate limiting |
| 📓 | **Ragas Evaluation** | Automated faithfulness, relevancy, and recall scoring via golden set |

</div>

---

## 🏗️ High-Level Architecture

```
Developer / GitHub Webhook
         |
         v
 Next.js App (frontend-next/)
         | HTTP REST
         v
 FastAPI Router (app/api/)
         |
         |──[Ingestion Pipeline]─────────────────────────────────┐
         |    1. Git Clone / Fetch  (app/ingestion/clone.py)      |
         |    2. File Filter        (file_filter.py)              |
         |    3. Tree-Sitter Parser (app/parsing/)                |
         |    4. AST Chunker        (chunker.py)                  |
         |    5a. Vector Store      (ChromaDB)                    |
         |    5b. BM25 Index        (app/retrieval/)              |
         |    5c. Call Graph        (NetworkX)                    |
         |                                                        |
         └──[Chat Agentic Loop]──────────────────────────────────┘
              Query ──> Semantic Answer Cache
                            | (miss)
                            v
                    RAG Agent Loop (app/agent/)
                            |
                            v
                    Agent Tools (tools.py)
                       |            |
                       v            v
               Hybrid Search    Graph Queries
              (RRF + Reranker)  (app/graph/)
                       \            /
                        \          /
                         v        v
                  Hallucination Guard (confidence.py)
                            |
                            v
                    Cache & Return → API
```

---

## ⚙️ Workflow Breakdowns

### Workflow 1 — Ingestion Pipeline

```
User / Webhook
     |
     | POST /ingest
     v
  API Layer ──── 202 Accepted {job_id}
     |
     | [Background Task]
     v
  clone_repo()
     |
     v
  filter_repo_files()   ← drops binaries, minified files, images
     |
     v
  parse_file()          ← Tree-Sitter AST extraction
     |
     v
  ┌──────────────────────────────────────┐
  │  [Parallel Indexing]                 │
  │  embed → ChromaDB (semantic)         │
  │  tokenize → BM25 (keyword)           │
  │  analyze → NetworkX (call graph)     │
  └──────────────────────────────────────┘
     |
     v
  metadata_store.update(status="synced")
```

**Key steps:**

| Step | What Happens |
|------|-------------|
| **Fast Return** | API returns `job_id` immediately — client is never blocked |
| **Safe Fetch** | Falls back to bundled dummy repo if network is unavailable |
| **Filtering** | Drops binaries, minified JS, images — saves LLM tokens |
| **AST Chunking** | Splits at class/function boundaries — context never chopped mid-logic |
| **Triple Indexing** | Semantic (ChromaDB) + Keyword (BM25) + Relational (NetworkX) simultaneously |

---

### Workflow 2 — Agentic Chat (RAG)

```
User Question
     |
     v
  Semantic Cache  ──── [HIT: similarity > 0.95] ──── Return cached answer
     |
  [MISS]
     |
     v
  Agent Loop (max 4 iterations)
     |
     | think → decide tool → call tool → observe result
     v
  ┌─────────────────────────────────────────┐
  │  search_code   → Hybrid Search (RRF)    │
  │  read_file     → Raw file contents      │
  │  get_callers   → Graph BFS upstream     │
  │  get_callees   → Graph BFS downstream   │
  │  generate_diagram → Mermaid output      │
  └─────────────────────────────────────────┘
     |
     | [context near limit → compress_older_tool_results()]
     v
  Final Answer
     |
     v
  Hallucination Guard
     |
     ├── confidence >= 4.0 → cache + return answer
     └── confidence < 4.0  → return safe fallback, gated=true
```

---

### Workflow 3 — Webhook Auto-Sync

```
GitHub Push / Merge Event
     |
     v
  POST /webhook
     |
     | Verify X-Hub-Signature-256 (HMAC)
     v
  Acquire write lock for repo_id
     |
     v
  Re-run full ingestion pipeline (force_reindex=True)
     |
     v
  invalidate_cache(repo_id)   ← purges ALL cached answers for this repo
     |
     v
  metadata_store.update(commit_hash=new_hash)
```

> **Why this matters:** HMAC-verified webhooks + write-locking + aggressive cache invalidation ensures the agent's answers always reflect the latest merged commit. Stale architectural explanations are never served.

---

## 📦 Module Reference

<details>
<summary><b>🌐 API Layer — app/api/ & app/main.py</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI bootstrap — middleware, exception handlers, router mount |
| `app/config.py` | Pydantic `BaseSettings` — single source of truth for env variables |
| `app/api/router.py` | REST endpoints: `/ingest`, `/status`, `/chat`, `/diagram` |
| `app/api/auth.py` | X-API-Key header authentication |
| `app/api/rate_limiter.py` | Sliding-window memory-based rate limiting on `/chat` |

</details>

<details>
<summary><b>⚙️ Ingestion Pipeline — app/ingestion/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `clone.py` | Git clone with size limits; offline fallback to dummy repo |
| `file_filter.py` | Allowlist: `.py`, `.js`, `.ts` — drops binaries and minified files |
| `metadata_store.py` | Persists sync state (`pending / synced / failed`) and commit hashes |
| `locking.py` | Thread-level locking per `repo_id` — prevents concurrent ingestion collisions |

</details>

<details>
<summary><b>🔬 Parsing & Chunking — app/parsing/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `tree_sitter_parser.py` | AST extraction of classes, functions, and imports via Tree-sitter grammars |
| `chunker.py` | Splits files at logical (class/function) boundaries — never mid-logic |

</details>

<details>
<summary><b>🗄️ Retrieval & Storage — app/retrieval/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `vector_store.py` | ChromaDB interface — stores and queries chunk embeddings |
| `bm25_store.py` | Pure-Python BM25 index — catches exact variable/function name matches |
| `embeddings.py` | SentenceTransformers wrapper for converting text to vectors |
| `hybrid_search.py` | Reciprocal Rank Fusion (RRF) combining vector + BM25 results |
| `reranker.py` | Cross-Encoder reranking of top-K hybrid search results |
| `query_expansion.py` | LLM-generated synonym/keyword expansion before hitting the index |

</details>

<details>
<summary><b>🕸️ Graph Operations — app/graph/ & app/diagrams/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `builder.py` | Builds a NetworkX directed graph of imports and internal function calls |
| `queries.py` | Timeout-safe BFS traversal for callers/callees (3-hop limit) |
| `mermaid_generator.py` | Converts a graph subgraph into a Mermaid diagram string for the frontend |

</details>

<details>
<summary><b>🤖 Agentic Loop — app/agent/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `loop.py` | Core execution loop — LLM call → tool intercept → tool run → feed back → repeat |
| `tools.py` | JSON schema definitions + retry logic for all 5 agent tools |
| `system_prompt.py` | LLM instructions: persona, rules, and strict markdown citation format |
| `semantic_cache.py` | 95% similarity threshold cache — same question, same commit → instant return |
| `context_manager.py` | Monitors token usage; condenses old tool results via secondary LLM |
| `confidence.py` | **Hallucination Guard** — validates every cited file/line; gates below score 4.0 |

</details>

<details>
<summary><b>🧪 Evaluation Suite — eval/</b></summary>

<br/>

| File | Responsibility |
|------|---------------|
| `run_eval.py` | Ragas automated evaluation: Faithfulness, Answer Relevancy, Context Precision, Context Recall |
| `compare_runs.py` | Compares new eval runs against previous baselines to detect regressions |

</details>

---

## 🔌 API Contracts

All routes require the `X-API-Key` header.

### `POST /ingest`

```json
// Request
{ "repo_url": "https://github.com/psf/requests", "ref": "main", "force_reindex": false }

// Response — 202 Accepted
{ "job_id": "abc-123", "status": "pending" }
```

### `GET /status/{repo_id}`

```json
{ "sync_status": "synced", "commit_hash": "a1b2c3d", "error": null, "has_circular_dependencies": false }
```

### `POST /chat`

```json
// Request
{ "repo_id": "psf_requests", "question": "How does session handling work?", "session_id": "opt-123" }

// Response
{
  "answer": "Session handling works by...",
  "sources": [
    { "file_path": "requests/sessions.py", "function_name": "Session.request", "start_line": 400, "end_line": 450 }
  ],
  "confidence_score": 9.5,
  "gated": false
}
```

### `POST /diagram`

```json
// Request
{ "repo_id": "psf_requests", "entry_point": "Session.request", "direction": "both" }

// Response
{ "mermaid_markdown": "graph TD\n..." }
```

<div align="center">

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ingest` | Start background ingestion of a repository |
| `GET` | `/status/{repo_id}` | Check ingestion / sync status |
| `POST` | `/chat` | Run the agentic RAG query loop |
| `POST` | `/diagram` | Generate a Mermaid call-graph diagram |

</div>

---

## 🛡️ Agentic Gating & Hallucination Guard

The Hallucination Guard (`confidence.py`) is the most critical safety feature. It parses the final LLM response for markdown citations (e.g. `` `src/auth.py:10-15` ``) and validates every single one against the actual index.

```
Final LLM Answer
       |
       v
Parse markdown citations (`file:start-end`)
       |
       v
For each citation:
  - Does file exist in index?        → No → penalize score
  - Are line numbers within bounds?  → No → penalize score
       |
       v
Compute deterministic confidence score (0–10)
       |
       ├── score >= 4.0 → return answer,  gated=false
       └── score < 4.0  → strip answer,   gated=true, return safe fallback
```

### Available Agent Tools

| Tool | Purpose |
|------|---------|
| `search_code` | Hybrid (vector + BM25) search with RRF fusion and Cross-Encoder reranking |
| `read_file` | Read raw file contents from the indexed repository |
| `get_callers` | Graph traversal: find functions that call a given function (3-hop limit) |
| `get_callees` | Graph traversal: find functions called by a given function (3-hop limit) |
| `generate_diagram` | Produce a Mermaid diagram from a graph subgraph |

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology | Role |
|-------|-----------|------|
| **Runtime** | Python 3.12 | Core language |
| **Backend** | FastAPI | REST API server, background tasks, auth |
| **Frontend** | Next.js 16 | Developer-facing chat and diagram UI |
| **LLM** | Groq (LLaMA 3) | Agent reasoning and answer generation |
| **Vector Store** | ChromaDB | Semantic embedding storage and search |
| **Keyword Index** | BM25 (pure Python) | Exact variable/function name matching |
| **Graph Engine** | NetworkX | Call graph — callers, callees, import chains |
| **AST Parser** | Tree-sitter | Language-aware code chunking |
| **Embeddings** | SentenceTransformers | Text-to-vector conversion |
| **Reranker** | Cross-Encoder | Relevance reranking of hybrid search results |
| **Evaluation** | Ragas | Automated faithfulness and recall scoring |
| **Webhooks** | HMAC SHA-256 | Secure GitHub push verification |

</div>

---

## 📁 Project Structure

```
📦 codebase-onboarding-agent/
│
├── 📂 app/
│   ├── 📂 api/
│   │   ├── 🔐 auth.py                  ← X-API-Key authentication
│   │   ├── 🚦 rate_limiter.py          ← Sliding-window rate limiting
│   │   └── 🛣️ router.py               ← /ingest /status /chat /diagram
│   │
│   ├── 📂 agent/
│   │   ├── 💬 loop.py                  ← Core agentic execution loop
│   │   ├── 🔧 tools.py                 ← Tool schemas + retry logic
│   │   ├── 📝 system_prompt.py         ← LLM instruction set
│   │   ├── ⚡ semantic_cache.py        ← 95% similarity answer cache
│   │   ├── 📏 context_manager.py       ← Token usage + compression
│   │   └── 🛡️ confidence.py           ← Hallucination guard + gating
│   │
│   ├── 📂 ingestion/
│   │   ├── 📥 clone.py                 ← Git clone + offline fallback
│   │   ├── 🔍 file_filter.py           ← Allowlist filtering
│   │   ├── 🗃️ metadata_store.py       ← Sync state + commit hash tracking
│   │   └── 🔒 locking.py              ← Thread-level repo locks
│   │
│   ├── 📂 parsing/
│   │   ├── 🌳 tree_sitter_parser.py    ← AST extraction
│   │   └── ✂️ chunker.py              ← Function/class boundary splitting
│   │
│   ├── 📂 retrieval/
│   │   ├── 🧮 vector_store.py          ← ChromaDB interface
│   │   ├── 🔡 bm25_store.py            ← BM25 keyword index
│   │   ├── 🧬 embeddings.py            ← SentenceTransformers wrapper
│   │   ├── 🔀 hybrid_search.py         ← RRF fusion
│   │   ├── 🎯 reranker.py              ← Cross-Encoder reranking
│   │   └── 💡 query_expansion.py       ← LLM synonym expansion
│   │
│   ├── 📂 graph/
│   │   ├── 🏗️ builder.py              ← NetworkX graph construction
│   │   └── 🔎 queries.py              ← BFS traversal (3-hop limit)
│   │
│   ├── 📂 diagrams/
│   │   └── 📊 mermaid_generator.py     ← Graph → Mermaid markdown
│   │
│   ├── ⚙️ config.py                   ← Pydantic BaseSettings (all env vars)
│   └── 🚀 main.py                     ← FastAPI bootstrap
│
├── 📂 frontend-next/
│   └── 🌐 app/workspace/            ← Next.js chat UI + diagram rendering
│
├── 📂 eval/
│   ├── 🧪 run_eval.py                 ← Ragas evaluation runner
│   └── 📈 compare_runs.py             ← Regression detection
│
├── 📂 tests/                          ← Full pytest suite
├── 🔧 .env.example                    ← Environment variable template
├── 🚀 run_local.bat                   ← One-command local startup
├── 📋 requirements.txt                ← All Python dependencies
└── 📖 README.md
```

---

## 🚀 Setup & Local Execution

### Prerequisites

```bash
python --version   # 3.12 required
git --version      # any recent version
```

### Step-by-Step Installation

**① Clone the repository**

```bash
git clone https://github.com/HurairaMaqbool/HurairaMaqbool.git
cd codebase-onboarding-agent
```

**② Create and activate a virtual environment**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

**③ Install all dependencies**

```bash
pip install -r requirements.txt
```

**④ Configure environment variables**

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY="your_groq_api_key"
LLM_PROVIDER="groq"
API_KEY="dev-secret-key"
WEBHOOK_SECRET="your_github_webhook_secret"
```

**⑤ Start the system**

```bash
run_local.bat
```

Or manually:

```bash
# Terminal 1 — backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Next.js UI
cd frontend-next && npm install && npm run dev
```

| Service | URL |
|---------|-----|
| FastAPI Backend | http://localhost:8000 |
| Next.js Frontend | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## 🧪 Testing

```bash
# Run the full test suite
pytest tests/

# Run a specific module
pytest tests/test_module_12.py -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html
```

> **Note:** `tests/test_golden_set.py` performs live API calls against real repositories. It is skipped by default to preserve API quotas — run explicitly when needed.

### Evaluation (Ragas)

```bash
python eval/run_eval.py        # Run full Ragas eval
python eval/compare_runs.py    # Compare against previous baseline
```

Metrics tracked: **Faithfulness · Answer Relevancy · Context Precision · Context Recall**

---

## 🛣️ Roadmap

```
 ✅  Phase 1 — Core Pipeline
     [x] Git ingestion + AST chunking
     [x] Triple indexing (ChromaDB + BM25 + NetworkX)
     [x] Hybrid search with RRF + reranker
     [x] Autonomous agentic loop (5 tools)

 ✅  Phase 2 — Safety & Reliability
     [x] Hallucination guard with citation validation
     [x] Semantic answer cache (95% threshold)
     [x] Context compression (token overflow protection)
     [x] HMAC-verified webhook auto-sync

 🔄  Phase 3 — Evaluation & Observability  (in progress)
     [ ] Ragas golden set scoring
     [ ] LangSmith tracing integration
     [ ] Regression detection pipeline

 🔮  Phase 4 — Extensions
     [ ] VS Code extension
     [ ] Multi-repo cross-codebase queries
     [ ] Docker containerisation + CI/CD
     [ ] Fine-tuned reranker on code-specific data
     [ ] Support for Go, Rust, Java (Tree-sitter grammar expansion)
```

---

## 🤝 Contributing

Contributions, ideas, and bug reports are warmly welcomed!

```bash
# 1. Fork the repository

# 2. Clone your fork
git clone https://github.com/YOUR-USERNAME/codebase-onboarding-agent.git

# 3. Create a feature branch
git checkout -b feature/your-feature-name

# 4. Make your changes and commit
git add .
git commit -m "feat: describe your change clearly"

# 5. Push and open a Pull Request
git push origin feature/your-feature-name
```

**Contribution ideas:**
- 🐛 Fix edge cases in `tree_sitter_parser.py` for multi-language repos
- ➕ Add Tree-sitter grammars for Go, Rust, or Java
- 🧪 Expand the Ragas golden set with new Q&A pairs
- 🐳 Add Docker + Docker Compose support
- 📊 Build a LangSmith observability dashboard

---

## 📄 Intellectual Property & Licensing

### 🔒 Copyright Notice
**Copyright © 2026 Huraira Maqbool. All Rights Reserved.**

This repository and all associated files—including but not limited to the Artificial Intelligence (AI) Agent Loop, prompt engineering templates, confidence gating guardrails, system architecture designs, and RAG retrieval algorithms—constitute the proprietary intellectual property of the author, **Huraira Maqbool**.

### 💼 Terms of Use
This repository is published exclusively for **learning, demonstration, and professional portfolio evaluation**. 
- **No Commercial Use:** You may not use this code or logic, in whole or in part, for any commercial activity or profit-generating business.
- **No Redistribution:** You are not permitted to host, distribute, or republish this codebase or any derivatives.
- **No Modifications or Reuse:** Direct copying, reuse of the AI prompting structure, or modification of the core retrieval systems without express written consent from the author is strictly prohibited.

For commercial licensing requests, collaboration inquiries, or permission to reuse components of this architecture, please contact:
📧 **hurairac37@gmail.com**

---

## 🛡️ Security & Responsible Usage

- **Educational Context:** This repository is intended to demonstrate architectural patterns and engineering best practices in RAG development.
- **Data Protection:** Ensure any deployment of this system complies with your organization's local data compliance standards. Do not load unvetted or sensitive internal credentials into public repository forks.
- **Vulnerability Reporting:** If you discover any security issues or potential vulnerabilities in this codebase, please refer to our [SECURITY.md](SECURITY.md) guidelines for instructions on safe, private disclosure.


---

## 👤 Author

<div align="center">

<br/>

<img src="https://github.com/HurairaMaqbool.png" width="110px" style="border-radius:50%; border: 3px solid #6E57F7;"/>

<br/>

### **Huraira Maqbool**
*AI Engineer · LangChain · LangGraph · RAG Pipelines · Agentic Systems*

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-HurairaMaqbool-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/HurairaMaqbool/HurairaMaqbool)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/huraira-maqbool-b696a5277/)
[![Email](https://img.shields.io/badge/Email-Contact-EA4335?style=for-the-badge&logo=gmail&logoColor=white)](mailto:hurairac37@gmail.com)

<br/>

*If this project saved you hours of onboarding time or taught you something new —
a ⭐ star on GitHub means a lot and helps other developers find it.*

<br/>

</div>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:24243e,50:302b63,100:0f0c29&height=120&section=footer" width="100%"/>

<sub>
Built with 🐍 Python · ⚡ FastAPI · 🧠 LangChain · 🕸️ NetworkX · ❤️ Passion for Developer Tooling
</sub>

</div>
