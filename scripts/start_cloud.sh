#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${STORAGE_ROOT:-/tmp/cwg-storage}"

export DEFER_INDEXING=true
python -m app.seed
unset DEFER_INDEXING
python -m app.reindex

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd /app/frontend
HOSTNAME=0.0.0.0 PORT="${PORT:-10000}" BACKEND_URL=http://127.0.0.1:8000 node server.js
