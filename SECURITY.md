# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest (main branch) | ✅ Supported |
| Any older branch | ❌ Not Supported |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Security issues in this codebase may affect users who self-host the application, expose sensitive repository data, or allow unauthorized API access. If you have discovered a vulnerability, please disclose it responsibly.

### How to Report

Send a private email to:

📧 **hurairac37@gmail.com**

Please include the following in your report:
- A clear description of the vulnerability
- The file(s) and line number(s) affected
- Steps to reproduce the issue
- The potential impact (data exposure, privilege escalation, denial of service, etc.)
- Any proof-of-concept code or screenshots, if applicable

### What to Expect

- **Acknowledgement:** Within 48 hours of receiving your report.
- **Assessment:** The severity and impact will be assessed within 5 business days.
- **Fix & Disclosure:** A patch will be released and a security advisory will be published after the fix is confirmed. Credit will be given to the reporter unless they prefer anonymity.

## Known Security Scope

The following are in scope for vulnerability reports:
- Authentication bypass on the `/chat`, `/ingest`, or `/status` endpoints
- API Key leakage or weak key validation
- Arbitrary file read/write via path traversal in the repository clone logic
- Webhook HMAC bypass
- Insecure pickle deserialization in the BM25 index loading logic

The following are **out of scope:**
- Vulnerabilities in third-party dependencies (report directly to the respective package maintainers)
- Local-only exploits that require physical machine access
- Rate limiting misconfigurations that do not lead to data exposure

## Security Best Practices for Operators

If you self-host CodeNavigator:
- Always set a strong, random `API_KEY` in your `.env` file (minimum 32 characters)
- Never expose the FastAPI backend (`port 8000`) directly to the public internet — place it behind a reverse proxy (e.g., Nginx) with TLS
- Rotate `GITHUB_WEBHOOK_SECRET` regularly
- Do not store sensitive credentials inside the cloned repositories directory (`repos/`)
