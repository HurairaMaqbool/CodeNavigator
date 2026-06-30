# Commercial Roadmap — Expert Plan to Full Production Sale

**Product:** CodeNavigator  
**Version:** 1.0 → 2.0 (commercial)  
**Last updated:** 2026-06-28

---

## Executive summary

| Dimension | Today | Target (v2.0) |
|-----------|-------|---------------|
| Technical product (RAG) | 8.5/10 | 9/10 |
| Commercial platform | 5.5/10 | 8/10 |
| Sellability (pilots) | 7/10 | 9/10 |
| Sellability (multi-tenant SaaS) | 4/10 | 7.5/10 |
| Enterprise (Fortune 500) | 2.5/10 | 6/10 (with Phase C) |

**Positioning today:** Self-hosted AI codebase onboarding for engineering teams.  
**Positioning v2.0:** Managed single-tenant + early multi-tenant SaaS.

---

## Phase A — P0 hardening (2–4 weeks) ✅ Complete

| # | Item | Status |
|---|------|--------|
| A1 | GitHub App tokens wired into clone | ✅ |
| A2 | OIDC JWKS signature verification | ✅ |
| A3 | OAuth state in Redis | ✅ |
| A4 | Tenant isolation (no cross-org keys) | ✅ |
| A5 | K8s ConfigMap Redis URL fix | ✅ |
| A6 | Honest docs (README/QA scores) | ✅ |
| A7 | Legal templates + SECURITY.md | ✅ |

---

## Phase B — P1 commercial MVP (6–10 weeks) ✅ Complete

| # | Item | Status |
|---|------|--------|
| B1 | **Postgres** for platform state | ✅ `DATABASE_URL` + JSON fallback |
| B2 | Stripe live price IDs + webhook tests | ✅ `STRIPE_PRICE_*`, `test_phase_b_platform.py` |
| B3 | Admin UI v2 (SSO link, create/revoke keys) | ✅ `admin/` |
| B4 | GitHub App install flow docs | ✅ existing integration |
| B5 | Platform integration test suite | ✅ phase A + B tests |
| B6 | K8s + Docker prod postgres profile | ✅ `--profile postgres` |

**Revenue unlock:** $500–$2k/mo per customer, 5–20 customers.

---

## Phase C — Enterprise (3–6 months) 🟡 Foundation

| # | Item | Status |
|---|------|--------|
| C1 | SAML + enterprise OIDC | 🟡 SAML metadata + OIDC fallback at `/saml/login` |
| C2 | SOC2-style controls doc | ✅ `docs/SOC2_CONTROLS.md` |
| C3 | SLA + status page | ✅ `GET /status/public` |
| C4 | Data residency options | 🟡 documented in SOC2 doc |
| C5 | HA Chroma / external vector DB | ⬜ future |

**Revenue unlock:** $50k+ annual contracts.

---

## Sellability matrix (updated)

| Buyer | Now | After Phase A | After Phase B |
|-------|-----|---------------|---------------|
| Internal team | 9/10 | 10/10 | 10/10 |
| Pilot (1–3 customers) | 7/10 | **8.5/10** | 9/10 |
| SMB self-hosted | 6.5/10 | 7.5/10 | 8.5/10 |
| Multi-tenant SaaS | 4/10 | 5/10 | **7.5/10** |
| Enterprise | 2.5/10 | 3/10 | 5/10 |

---

## Pricing guidance

| Tier | Price | Includes |
|------|-------|----------|
| Pilot | $5k–$15k one-time | Self-hosted, manual setup, 30-day support |
| Pro (managed) | $500–$1.5k/mo | Single tenant, updates, backup |
| Team | $1.5k–$3k/mo | SSO, audit, SLA-lite |
| Enterprise | Custom $50k+/yr | SAML, DPA, dedicated infra |

---

## Implementation checklist (engineering)

```
Phase A (this sprint)
  [x] Roadmap doc (docs/COMMERCIAL_ROADMAP.md)
  [x] clone.py + github_app clone_auth
  [x] oidc JWKS + Redis OAuth state
  [x] platform_router tenant fix
  [x] k8s configmap fix
  [x] README/QA honest scores
  [x] tests/test_phase_a_hardening.py
  [x] Postgres schema + optional docker profile

Phase B (next)
  [ ] DATABASE_URL + Postgres docker
  [ ] app/platform/db/ store abstraction
  [ ] Stripe E2E tests
  [ ] Admin OIDC login
```

---

## What NOT to claim in sales until Phase B

- Multi-tenant SaaS at unlimited scale
- SOC2 certified
- Counsel-approved legal package
- 99.9% SLA

## What you CAN claim today (after Phase A)

- Production RAG pipeline with 349+ tests
- Self-hosted Docker deploy in under 1 hour
- API key auth, GDPR purge, audit trail
- GitHub webhook auto-reindex
- Optional Stripe billing (when configured)
