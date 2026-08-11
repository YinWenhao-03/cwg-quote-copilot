#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${STORAGE_ROOT:-/tmp/cwg-storage}"

# Open the public port immediately so Render can pass its health check while the
# demo data and remote embedding index are prepared in the background.
cd /app/frontend
HOSTNAME=0.0.0.0 PORT="${PORT:-10000}" BACKEND_URL=http://127.0.0.1:8000 node server.js &
frontend_pid=$!
cd /app/backend

export DEFER_INDEXING=true
python -m app.seed
unset DEFER_INDEXING
python -m app.reindex

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cleanup() {
  kill "$frontend_pid" "${backend_pid:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait "$frontend_pid" "$backend_pid"
