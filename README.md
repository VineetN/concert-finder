# Concert Finder

> Seattle live music ranked to your taste — not the algorithm's.

Pulls upcoming Seattle shows, enriches every artist on the bill with Spotify metadata and Last.fm genre data, clusters your listening history into 2–4 taste modes, and scores events by predicted enjoyment. Surfaces **safe bets** (strong match to your dominant taste) and **stretch picks** (strong match to a secondary taste). Includes a **Taste Map** — a UMAP projection of your top artists and upcoming headliners, coloured by taste cluster.

## Stack

| Layer | Choice |
|-------|--------|
| Python env | `uv` workspaces |
| Backend | FastAPI + uvicorn |
| Frontend | Next.js 14 (App Router) + Tailwind + shadcn |
| Database | SQLite + `sqlite-vec` |
| DB sync | Litestream → Cloudflare R2 |
| Embeddings | `BAAI/bge-small-en-v1.5` (local, CPU) |
| Clustering | HDBSCAN → KMeans fallback |
| Scheduling | APScheduler (in-process) |
| Process mgmt | pm2 |
| Auth | NextAuth v5 (Spotify provider) |
| Genre enrichment | Last.fm API |
| Explanations | HuggingFace Inference API (`Qwen/Qwen2.5-72B-Instruct`) |

## Venues covered

8 scrapers run nightly. Songkick aggregates shows across many Seattle venues; the remaining scrapers target specific clubs directly:

| Scraper | Coverage |
|---------|----------|
| Songkick | Aggregator — broad Seattle show calendar |
| Neumos | Neumos / Moe Bar |
| Crocodile | The Crocodile |
| Sunset Tavern | Sunset Tavern |
| Showbox SoDo | Showbox SoDo |
| Chop Suey | Chop Suey |
| Tractor Tavern | Tractor Tavern |
| Barboza | Barboza |

## Two-node setup

```
Node A (ingestion)          Node B (serving)
─────────────────           ──────────────────
scraper worker              FastAPI + Next.js
  ↓ nightly 3am PT            ↓ reads from DB
SQLite DB  ──→ Litestream ──→ R2 ──→ restored on Node B
```

If Node A is down, Node B keeps serving stale data.
If Node B is down, ingestion still runs.

## Prerequisites

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Node 20+, [`pnpm`](https://pnpm.io/installation) (`npm i -g pnpm`)
- [`just`](https://just.systems/man/en/packages.html)
- Spotify developer app → [create one](https://developer.spotify.com/dashboard)
- Last.fm API key → [create one](https://www.last.fm/api/account/create) (free, no callback needed)

## Setup

```bash
git clone https://github.com/VineetN/concert-finder
cd concert-finder
just install
```

**Two env files are required** — one for the Python services, one for Next.js:

```bash
# 1. Root .env — read by FastAPI, worker, and scrapers
cp .env.example .env
# Fill in: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, NEXTAUTH_SECRET,
#          AUTH_SECRET (same as NEXTAUTH_SECRET), LASTFM_API_KEY

# 2. apps/web/.env.local — read by Next.js
cp apps/web/.env.local.example apps/web/.env.local
# Fill in the same Spotify + auth values
```

In your **Spotify app dashboard**, add this redirect URI:
```
http://127.0.0.1:3000/api/auth/callback/spotify
```
> Use `127.0.0.1`, not `localhost` — Spotify's OAuth explicitly blocks `localhost`.

## Running (dev)

```bash
just api      # FastAPI on :8000
just web      # Next.js on :3000
just scrape   # run ingestion pipeline once (populates the DB)
just worker   # start the APScheduler worker (nightly scrapes on Node A)

# Quality
just test
just lint
just fmt
```

Open `http://127.0.0.1:3000`, sign in with Spotify, and click **Sync** to cluster your listening history. Events appear immediately after sync.

## Project structure

```
concert-finder/
├── apps/
│   ├── api/          # FastAPI backend
│   └── web/          # Next.js frontend
├── packages/
│   ├── ingest/       # scrapers + Spotify enrichment
│   ├── scoring/      # taste clustering + match scoring
│   └── shared/       # SQLModel schemas (shared types)
├── worker/           # APScheduler entry point (Node A)
├── infra/            # Litestream config, Tailscale notes
└── data/             # SQLite DB (gitignored — synced via Litestream)
```

## Scoring

Each event is scored against each of the user's taste modes (HDBSCAN clusters of their Spotify top artists). Final score = max cosine similarity across all (artist × mode) pairs, weighted by billing position (headliner 1.0 / direct support 0.7 / opener 0.5).

- **Safe Bet** — sim > 0.73 against dominant taste mode
- **Stretch Pick** — sim > 0.70 against a secondary mode
- **Regular** — everything else

## License

MIT
