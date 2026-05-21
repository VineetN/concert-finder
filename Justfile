# Concert Finder — task runner
# Install: https://just.systems/man/en/packages.html

default:
    @just --list

# ── Dev ───────────────────────────────────────────────────────────────────────

# Start FastAPI backend with hot reload
api:
    uv run --project apps/api uvicorn concert_finder_api.main:app --reload --port 8000

# Start Next.js frontend
web:
    pnpm --filter web dev

# Start ingestion worker (scheduled at 3am PT)
worker:
    uv run python worker/worker.py

# Run scraper pipeline immediately (bypasses schedule)
scrape:
    uv run python worker/worker.py --run-now

# ── Install ───────────────────────────────────────────────────────────────────

# Install all Python + Node deps
install:
    uv sync
    pnpm install

# ── Quality ───────────────────────────────────────────────────────────────────

test:
    uv run pytest

lint:
    uv run ruff check .
    uv run pyright .

fmt:
    uv run ruff format .

# ── DB ────────────────────────────────────────────────────────────────────────

# Node B: restore latest DB snapshot from R2
db-pull:
    litestream restore -config infra/litestream.yml data/concert.db

# Node A: start continuous replication to R2
db-replicate:
    litestream replicate -config infra/litestream.yml
