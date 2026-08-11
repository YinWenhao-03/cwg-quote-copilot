.PHONY: setup setup-full seed reindex dev test benchmark clean

setup:
	uv sync --project backend --extra dev
	pnpm --dir frontend install
	cp -n .env.example .env || true

setup-full:
	uv sync --project backend --extra dev --extra full
	pnpm --dir frontend install
	cp -n .env.example .env || true

seed:
	uv run --project backend python -m app.seed

reindex:
	uv run --project backend python -m app.reindex

dev:
	uv run --project backend python scripts/dev.py

test:
	uv run --project backend python -m app.seed
	uv run --project backend pytest backend/tests -q
	pnpm --dir frontend test

benchmark:
	uv run --project backend python -m app.benchmark --sizes 1000 10000 50000

clean:
	uv run --project backend python -m app.reset_local
