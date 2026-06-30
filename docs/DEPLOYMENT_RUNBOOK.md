# Deployment Runbook

## Production deploy

```bash
cp .env.example .env
# Set: GROQ_API_KEY, API_KEY (24+ chars), GITHUB_WEBHOOK_SECRET, REDIS_PASSWORD
# Set: ENVIRONMENT=production

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Verify:

```bash
curl http://localhost:8000/health
curl -H "X-API-Key: $API_KEY" http://localhost:8000/ready
```

## Backup

| Asset | Path / service |
|-------|----------------|
| Repos + metadata | `data/repos/` |
| Chroma vectors | Docker volume `chroma_data` or `data/chroma_db/` |
| BM25 | `bm25_index/` volume |
| Graphs | `data/graph_store/` |
| Audit log | `data/audit_log.jsonl` |
| API keys | `data/api_keys.json` |

```bash
# Example tarball backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/ bm25_index/ tests/golden_set_status.json
```

## Restore

1. Stop stack: `docker compose -f docker-compose.prod.yml down`
2. Restore volumes / `data/` from backup
3. Start stack and run health + golden CI smoke test

## GDPR delete (customer offboarding)

```bash
curl -X DELETE -H "X-API-Key: $API_KEY" \
  http://localhost:8000/platform/repos/{job_id}
```

## Create per-org API key

```bash
curl -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"org_id":"acme","label":"production"}' \
  http://localhost:8000/platform/api-keys
```

## TLS

Terminate HTTPS at nginx/Caddy/ALB; proxy to backend `:8000` and Streamlit `:8501`.
