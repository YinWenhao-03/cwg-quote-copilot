FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONPATH=/app/backend
WORKDIR /app

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN pip install --no-cache-dir uv
COPY backend/ backend/
RUN uv sync --project backend --frozen --no-dev
COPY --from=frontend-builder /build/frontend/.next/standalone/ frontend/
COPY --from=frontend-builder /build/frontend/.next/static/ frontend/.next/static/
COPY scripts/start_cloud.sh scripts/start_cloud.sh
RUN chmod +x scripts/start_cloud.sh

ENV PORT=10000 \
    BACKEND_URL=http://127.0.0.1:8000 \
    STORAGE_ROOT=/tmp/cwg-storage \
    DATABASE_URL=sqlite:////tmp/cwg-storage/cwg.db \
    QDRANT_PATH=/tmp/cwg-storage/qdrant \
    FRONTEND_ORIGIN=http://localhost:10000

EXPOSE 10000
CMD ["/app/scripts/start_cloud.sh"]
