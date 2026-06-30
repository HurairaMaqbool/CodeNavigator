# Commercial Readiness — 10/10 Checklist

## Product tiers

| Plan | Chat/mo | Ingest/mo | Eval/mo | Price |
|------|---------|-----------|---------|-------|
| Free | 100 | 5 | 10 | $0 |
| Pro | 2,000 | 50 | 100 | $49 |
| Team | 10,000 | 200 | 500 | $199 |

## API surface

| Endpoint | Purpose |
|----------|---------|
| `/platform/*` | GDPR, audit, usage, API keys |
| `/billing/*` | Plans, checkout, subscription |
| `/auth/*` | OIDC SSO |
| `/webhook/stripe` | Billing lifecycle |
| `/webhook/github-app` | App installs + push |

## Deploy stack

```bash
docker compose -f docker-compose.prod.yml up -d
# API :8000 | Streamlit :8501 | Admin :3000
```

## Pilot onboarding (30 min)

1. Set production `.env` (API_KEY, GROQ, webhook secrets)
2. Deploy Docker prod profile
3. `POST /platform/api-keys` for customer org
4. Optional: configure Stripe price IDs + OIDC issuer
5. Install GitHub App → webhook to `/webhook/github-app`

## Remaining for Fortune 500

- Postgres for multi-replica state (JSON stores → DB)
- SOC2 controls + formal DPA review
- Managed SLA + status page
