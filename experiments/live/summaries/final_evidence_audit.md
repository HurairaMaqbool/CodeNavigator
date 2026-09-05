# Final Evidence Audit & Experimental Validation Report

## 1. Executive Summary & Final Verdict

### FINAL EXPERIMENTAL VERDICT: **CONDITIONAL GO**

The live rerun of **EXP-A (Full CodeNavigator System)** and frozen **EXP-B (Naive Dense RAG)** baseline artifacts have been audited directly from primary filesystem evidence. All 27 queries ran to completion in both systems. Quantitative findings can be reported in a research paper under the condition that EXP-A's verification gating behavior is disclosed as an explicit precision-over-recall trade-off.

## 2. Completeness Audit

Both `exp_a_full_system_live.json` and `exp_b_naive_dense_rag_live.json` contain exactly 27 complete records with unique query IDs (`gs_ingest_001` through `gs_hall_002`), full answer text, retrieval hits, and timing metrics.

| Metric | EXP-A (Full System) | EXP-B (Naive Dense Baseline) |
| :--- | :---: | :---: |
| **Total Benchmark Queries** | 27 | 27 |
| **Completed Records** | 27 (100%) | 27 (100%) |
| **Ungated Verified Answers** | 6 (22.2%) | 27 (100%) |
| **Gated / Abstained Answers** | 21 (77.8%) | 0 (0.0%) |

## 3. Parser Repair & Unit Testing

The client-side JSON parser fix (`strip_json_fences` stripping `<think>...</think>` tags in `app/agent/grounding.py`) was verified via `tests/test_finalize_prompt_parser.py` (5/5 unit tests passed). In the live EXP-A rerun, Groq HTTP requests returned 200 OK across all queries.

## 4. Key Performance Metrics (Recomputed from Primary Data)

* **Retrieval Hit@5**:
  * **EXP-A (Hybrid + Reranking)**: **96.3%** (26 / 27 queries retrieved $\ge 1$ ground-truth file in top-5)
  * **EXP-B (Dense Vector Only)**: **85.2%** (23 / 27 queries retrieved $\ge 1$ ground-truth file in top-5)
  * **Difference ($\Delta$)**: **+11.1 percentage points**

* **Answer Factual Accuracy**:
  * **EXP-B (Naive Dense RAG - Ungated)**: **77.8%** (21 / 27) (95% CI: `[63.0%, 92.6%]`)
  * **EXP-A (Full CodeNavigator - Gated)**: **18.5%** (5 / 27) (95% CI: `[3.7%, 33.3%]`)
  * **Statistical Significance**: McNemar exact test $p = 1.77 \times 10^{-4}$ ($\chi^2_{\text{uncorrected}} = 16.0$).

## 5. Latency Audit

* **EXP-A Latency**: Mean = `28.53s`, Median = `24.88s`, Min = `0.10s`, Max = `60.76s` (reflecting multi-turn agent execution and rate-limit sleeps).
* **EXP-B Latency**: Mean = `12.87s`, Median = `13.02s`, Min = `0.79s`, Max = `37.85s`.

## 6. Paper Readiness Summary

* **Ready for Publication**:
  1. High-precision retrieval comparison (Hit@5 96.3% vs 85.2%).
  2. Baseline factual performance of Naive Dense RAG (77.8%).
  3. Empirical demonstration of verification gating behavior under reasoning model outputs.
