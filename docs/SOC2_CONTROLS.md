# SOC 2 Controls Mapping (Type II readiness outline)

**Product:** CodeNavigator  
**Version:** 2.0 commercial  
**Status:** Internal control framework — not a SOC 2 report. Engage a CPA firm for formal attestation.

---

## Trust Service Criteria overview

| TSC | Control area | Implementation in product |
|-----|--------------|---------------------------|
| CC6 | Logical access | API keys per org, OIDC SSO, production key enforcement, path jail |
| CC7 | System operations | `/health`, `/ready`, `/status/public`, structured logging, Sentry optional |
| CC8 | Change management | Git + CI tests, Docker/K8s manifests, deployment runbook |
| C1 | Confidentiality | Tenant isolation (org-scoped keys, usage, audit), GDPR purge/export |
| P1 | Privacy | Audit log, data export, subscription metadata minimization |

---

## CC6 — Access control

| Control | Evidence |
|---------|----------|
| Unique credentials per tenant | `POST /platform/api-keys`, Postgres `api_keys` table |
| Revocation | `DELETE /platform/api-keys`, `revoke_api_key()` |
| SSO for operators | OIDC `/auth/login`, optional SAML metadata at `/saml/metadata` |
| Production weak-key block | `is_production_api_key_valid()` at startup |
| Metrics/docs protection | `PROTECT_METRICS`, `DISABLE_OPENAPI_IN_PRODUCTION` |

**Gap:** SAML assertion handling requires `python3-saml` + IdP-specific QA.

---

## CC7 — Monitoring

| Control | Evidence |
|---------|----------|
| Liveness | `GET /health` |
| Readiness | `GET /ready` (Chroma, Redis, Postgres) |
| Public status | `GET /status/public` |
| Audit trail | `GET /platform/audit`, `audit_events` table |
| Usage metering | `GET /platform/usage` |

**Gap:** Formal uptime SLA and external status page (e.g. Statuspage) not bundled.

---

## CC8 — Change & deployment

| Control | Evidence |
|---------|----------|
| Automated tests | `pytest` suite (350+ tests) |
| Container images | `Dockerfile`, `docker-compose.prod.yml` |
| K8s | `k8s/` manifests |
| Runbook | `docs/DEPLOYMENT_RUNBOOK.md` |

---

## C1 / P1 — Data handling

| Control | Evidence |
|---------|----------|
| Right to erasure | `DELETE /platform/repos/{repo_id}` |
| Data portability | `GET /platform/repos/{repo_id}/export` |
| Tenant data separation | Org-scoped API keys and usage in Postgres |
| Secrets | Env-based config, K8s Secrets for Redis/DB |

**Gap:** Counsel-reviewed DPA/subprocessor list in `docs/legal/` — templates only.

---

## Recommended next steps for audit

1. Penetration test on `/platform/*` and webhook endpoints.
2. Enable Postgres in production (`DATABASE_URL` + `--profile postgres`).
3. Wire Stripe live mode with webhook signing secret rotation procedure.
4. Document incident response in `SECURITY.md` (owner + 24h contact).
5. Commission SOC 2 Type I readiness assessment with your CPA.

---

## Data residency

Deploy separate stacks per region (EU/US) with:

- `DATABASE_URL`, `CHROMA_HOST`, `REPOS_PATH` isolated per region
- `ENVIRONMENT=production` and region label in audit `details`

No cross-region replication is implemented by default.
