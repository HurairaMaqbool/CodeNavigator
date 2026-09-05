# Final Claim-Evidence Matrix

| Claim | Primary Evidence Artifact | Calculation / Source | Status | Safe Paper Wording |
| :--- | :--- | :--- | :---: | :--- |
| **Benchmark Query Alignment** | `exp_a_full_system_live.json`, `exp_b_naive_dense_rag_live.json` | 27/27 string-matched question texts and ground-truth targets | **VERIFIED** | "The evaluation was conducted on a paired 27-query Golden Set benchmark across both systems." |
| **EXP-B Factual Accuracy** | `exp_b_naive_dense_rag_live.json` | 21 / 27 correct answers under ground-truth keyword rubric | **VERIFIED** | "The naive dense RAG baseline achieved 77.8% (21/27) factual accuracy when ungated." |
| **EXP-A Verification Gating Behavior** | `exp_a_full_system_live.json` | 21 / 27 responses gated (`gated=True`) due to missing structured citations | **VERIFIED** | "With strict verification gating enabled, CodeNavigator abstained on 21/27 queries when structured citations were unverified." |
| **EXP-A Ungated Factual Accuracy** | `exp_a_full_system_live.json` | 5 / 27 correct un-gated answers | **VERIFIED** | "CodeNavigator delivered 18.5% (5/27) ungated verified answers, abstaining on unverified queries." |
| **Retrieval Hit@5 Performance** | `exp_a_full_system_live.json`, `exp_b_naive_dense_rag_live.json` | EXP-A Hit@5: 96.3% (26/27), EXP-B Hit@5: 85.2% (23/27) | **VERIFIED** | "Hybrid search with reranking achieved Hit@5 of 96.3% compared to 85.2% for dense vector search." |
| **Statistical Significance of Gating Delta** | `exp_a_full_system_live.json`, `exp_b_naive_dense_rag_live.json` | McNemar test: $b=0, c=16, \chi^2=16.0, p=1.77 \times 10^{-4}$ | **VERIFIED** | "The difference in ungated accuracy between naive dense RAG and gated verification was statistically significant (McNemar $p < 0.001$)." |
| **System Latency** | `exp_a_full_system_live.json`, `exp_b_naive_dense_rag_live.json` | EXP-A mean latency: 28.53s (including rate-limit sleep), EXP-B mean: 12.87s | **VERIFIED** | "Full agent execution incurred higher average latency (28.5s vs 12.9s) due to multi-step reasoning and API rate-limit backoffs." |
