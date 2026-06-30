# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |

## Reporting a vulnerability

Email security issues to your organization's security contact (replace before public launch).

Please include:
- Description and impact
- Steps to reproduce
- Affected version / commit

Do **not** open public GitHub issues for undisclosed vulnerabilities.

## Security controls (v1.0)

- API key authentication on all business endpoints
- Path jail on `read_file` agent tool (blocks `../` traversal)
- GitHub webhook HMAC-SHA256 verification
- Rate limiting on ingest, chat, and webhooks
- Secret masking in indexed chunks
- Production validation for `API_KEY` and `GITHUB_WEBHOOK_SECRET`
- Optional `/metrics` protection in production
- GDPR purge API: `DELETE /platform/repos/{repo_id}`

## Hardening checklist for operators

1. Set `ENVIRONMENT=production`
2. Use a strong `API_KEY` (24+ characters) or per-org keys via `POST /platform/api-keys`
3. Set `GITHUB_WEBHOOK_SECRET`
4. Do not expose Redis/Chroma ports publicly
5. Terminate TLS at a reverse proxy (nginx, Caddy, cloud LB)
