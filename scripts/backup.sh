#!/usr/bin/env bash
# Backup script for self-hosted deployments
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backup-${STAMP}.tar.gz"
echo "Creating ${OUT}..."
tar -czf "${OUT}" data/ bm25_index/ tests/golden_set_status.json 2>/dev/null || \
  tar -czf "${OUT}" data/ bm25_index/ 2>/dev/null || true
echo "Done: ${OUT}"
