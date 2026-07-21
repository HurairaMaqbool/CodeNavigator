# Production Deployment Verification Checklist

This checklist must be executed prior to any production release to guarantee that the 7 critical grounding, concurrency, and security vulnerabilities audited in July 2026 do not regress.

## 1. Security & Isolation Checks
- [ ] **Cross-Repo Contamination Guard:** Verify `EXCLUDED_DIRS` in `app/ingestion/file_filter.py` contains `data` and `repos`.
  * *Verification*: Check line 54+ for the presence of `"data", "repos"` inside the frozenset.
  * *Test*: Ensure `requests` source code ingested via tests does not bleed into the `repo_id` of the primary indexed codebase by searching for external signatures (`requests/api.py`).
- [ ] **Path Traversal Guard:** Verify `_validate_repo_id` in `app/api/router.py`.
  * *Verification*: Confirm the regex is strictly `^(?:[a-fA-F0-9]{64}|public)$`.
  * *Test*: Issue `GET /api/v1/symbols/12345/..//` and assert it returns HTTP 400 Bad Request.

## 2. Concurrency & Artifact Lifecycle
- [ ] **BM25 Race Conditions:** Verify lock striping in `app/retrieval/bm25_store.py`.
  * *Verification*: Ensure `_get_repo_lock(repo_id)` uses the global `_LOCK_MAP_LOCK` to issue per-repo `threading.Lock`s.
  * *Test*: Ensure read methods (`load_bm25_index`) and write methods (`save_bm25_index`) both acquire this lock before mutating the cache or disk.
- [ ] **Stale Index Artifacts:** Verify teardown hooks on re-index.
  * *Verification*: Confirm `vector_store.py` calls `client.delete_collection(collection_name)` during `force_reindex=True`.
  * *Verification*: Confirm `bm25_store.py` calls `pkl_path.unlink(missing_ok=True)`.
  * *Verification*: Confirm `graph/builder.py` uses `os.replace()` for atomic graph artifact replacement.

## 3. Grounding & Verification Pipeline
- [ ] **False Positives (Vague Stems):** Verify Lexical Layer 2 in `app/agent/claim_verification.py`.
  * *Verification*: Ensure `_COMMON_PROGRAMMING_WORDS` remains active and includes terms like `"client"`, `"header"`, `"function"`, and `"auth"`.
  * *Test*: Validate that overlap scores accurately reflect domain-specific terms rather than common syntax.
- [ ] **Grounding Over-Correction (False Negatives):** Verify AST Gate in `app/agent/claim_verification.py`.
  * *Verification*: Ensure `_check_ast_symbol_grounding()` handles layer 5 verification using `tree-sitter`, explicitly identifying candidate symbols in the syntax tree rather than relying on unreliable LLM entailment checking.
- [ ] **Behavioral & Numeric Hallucinations:** Verify Literal Gate in `app/agent/claim_verification.py`.
  * *Verification*: Ensure `_check_literal_grounding()` (Layer 7) enforces regex bounds `\b\d+\b` and boolean keywords (`True`, `False`, `None`) against the cited chunk.
- [ ] **Rate Limit Handling:** Verify graceful fallbacks on API throttling.
  * *Verification*: Ensure that `method: "entailment_fail"` does not exist in the codebase anymore, avoiding catastrophic gating cascades caused by external API rate limits.
