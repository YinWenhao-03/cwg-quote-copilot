#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${STORAGE_ROOT:-/tmp/cwg-storage}"

if [[ "${APP_ENV:-development}" == "production" && "${APP_SECRET:-development-only-change-me}" == "development-only-change-me" ]]; then
  export APP_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi

# Open the public port immediately; Render keeps the previous instance active
# until the proxied backend health check passes after indexing is complete.
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
