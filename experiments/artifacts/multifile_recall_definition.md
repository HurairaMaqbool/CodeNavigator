# Definition of Multi-File Context Recall

## Mathematical Formulation

Multi-File Context Recall ($\text{Recall}_{\text{multi}}$) measures the proportion of multi-file dependency queries for which all required cross-file reference contexts are successfully retrieved into the LLM context window.

$$\text{Recall}_{\text{multi}} = \frac{\sum_{i \in Q_{\text{multi}}} \mathbb{I}(\mathcal{R}_i \supseteq \mathcal{G}_i)}{|Q_{\text{multi}}|}$$

Where:
- $Q_{\text{multi}}$: The subset of evaluation queries whose ground truth involves symbols or call hierarchies spanning two or more distinct source files ($|Q_{\text{multi}}| = 19$).
- $\mathcal{R}_i$: The set of file paths retrieved by the system for query $i$.
- $\mathcal{G}_i$: The set of ground-truth relevant file paths required to completely answer query $i$.
- $\mathbb{I}(\cdot)$: Indicator function returning $1$ if retrieved files cover ground-truth files, and $0$ otherwise.

## Calculation Protocol

1. **Numerator**: Count of multi-file queries where $\mathcal{R}_i \supseteq \mathcal{G}_i$.
2. **Denominator**: Total number of multi-file queries ($|Q_{\text{multi}}| = 19$).
3. **Eligible Queries**: Excludes single-file queries (5) and non-existent feature hallucination traps (2).
4. **Graph Impact**: Graph augmentation expands node traversal across import/call edges ($u \to v$), increasing $\text{Recall}_{\text{multi}}$ from 42.11% (Graph OFF) to 63.16% (Graph ON).
