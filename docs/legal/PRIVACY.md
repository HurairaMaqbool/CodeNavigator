# Privacy Policy (Template)

**Last updated:** 2026-06-28

This template is for self-hosted / single-tenant deployments. Customize before commercial sale.

## Data we process

- Repository source code (ingested from GitHub URLs you provide)
- Questions you ask the agent
- API usage metadata (audit log, optional usage metering)

## Data storage

Data is stored on infrastructure you control (local disk, Chroma, Redis).

## Your rights (GDPR)

- **Export:** `GET /platform/repos/{repo_id}/export`
- **Delete:** `DELETE /platform/repos/{repo_id}`

## Subprocessors

- Groq (LLM inference) when `LLM_PROVIDER=groq`
- GitHub (repository cloning)

## Contact

Replace with your company contact email.
