# EXP-B Live Naive Dense RAG Independent Forensic Audit Report

## 1. Artifact Integrity
- **File**: experiments\live\raw\exp_b_naive_dense_rag_live.json
- **Size**: 61661 bytes
- **MD5**: bda9a7bdb08a2fbe78fb0fbe9af3af13
- **SHA-256**: a51a4e5c13b55a8a2be5714f92fa5b17febf1204350eca49baf0f4f8a51a62e2
- **Total Records**: 27
- **Unique Query IDs**: 27
- **Required Fields Validated**: True

## 2. Execution Configuration
- **Embedding Model**: ll-MiniLM-L6-v2
- **LLM Model**: qwen/qwen3.6-27b (Groq API)
- **Top-K**: 5
- **Sparse BM25**: Disabled
- **Reciprocal Rank Fusion (RRF)**: Disabled
- **Cross-Encoder Reranker**: Disabled
- **Call Graph Traversal**: Disabled
- **Verification Gating / Intent Firewall**: Disabled

## 3. Retrieval & Failure Breakdown
- **Total Benchmark Queries**: 27
- **Infrastructure Failures**: 0
- **Retrieval Failures (Missed GT Files)**: 5
- **Dense Retrieval Hit@5**: 81.5%

## 4. Latency Distribution
- **Mean Latency**: 11.71s
- **Median Latency**: 13.01s
- **Std Dev**: 12.7s
- **Min / Max**: 0.79s / 37.85s
- **P95 Latency**: 37.68s

## 5. Critical Audit Verdicts
- **LIVE EXECUTION**: GO
- **RAW DATA**: GO
- **RETRIEVAL EVALUATION**: GO
- **ANSWER EVALUATION**: NO-GO (Requires full expert human adjudication on answer semantic completeness beyond file overlap)
- **CONFUSION-MATRIX METRICS**: NO-GO (Forcing retrieval overlap into binary confusion matrix without gating/confidence rubrics is statistically invalid)
- **LATENCY METRICS**: GO
- **PAPER USABILITY**: GO (As an empirical baseline for dense retrieval failure modes)
- **EXP-A vs EXP-B COMPARISON**: NO-GO (EXP-A evaluated full agent with gating/confidence rubrics; EXP-B evaluates un-gated naive retrieval output)
