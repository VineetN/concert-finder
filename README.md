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
- HuggingFace account → [create a token](https://huggingface.co/settings/tokens) (free; enables match explanations and avoids rate limits on model downloads)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/VineetN/concert-finder
cd concert-finder
just install
```

### 2. Configure environment

Two env files are required — one for Python services, one for Next.js:

```bash
cp .env.example .env
cp apps/web/.env.local.example apps/web/.env.local
```

Fill in `.env` (read by FastAPI, worker, and scrapers):

| Variable | Why it's needed | Where to get it |
|----------|----------------|-----------------|
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` | User login via Spotify OAuth, plus nightly artist enrichment (name → metadata) | [Create a Spotify app](https://developer.spotify.com/dashboard) → Settings → copy Client ID and Secret |
| `NEXTAUTH_SECRET` / `AUTH_SECRET` | Signs and encrypts the user session cookie — without this Auth.js refuses to start | Generate locally: `openssl rand -base64 32` — paste the same value into both variables |
| `LASTFM_API_KEY` | Fetches crowd-sourced genre tags for artists — Spotify removed genre data from its API in Nov 2024, so this fills the gap | [Last.fm API account](https://www.last.fm/api/account/create) — free, no callback URL needed |
| `HF_TOKEN` | Downloads the local embedding model without hitting rate limits; also powers the one-sentence "why this match" explanations via the free Inference API | [HuggingFace → Settings → Tokens](https://huggingface.co/settings/tokens) → New token (read access is enough) |
| `TICKETMASTER_API_KEY` | Optional — covers WaMu Theater, Climate Pledge Arena, White River Amphitheatre, and all other Live Nation venues in the Seattle metro. Without it those venues are skipped. | [developer.ticketmaster.com](https://developer.ticketmaster.com) → My Apps → Consumer Key (free, 5,000 calls/day) |

Fill in `apps/web/.env.local` with the same `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `NEXTAUTH_SECRET`, and `AUTH_SECRET`. The `AUTH_URL` and `API_URL` are pre-filled in the example and work for local dev as-is.

### 3. Add the Spotify redirect URI

In your [Spotify app dashboard](https://developer.spotify.com/dashboard), add this redirect URI:

```
http://127.0.0.1:3000/api/auth/callback/spotify
```

> Use `127.0.0.1`, not `localhost` — Spotify's OAuth explicitly blocks `localhost`.

### 4. First run

Run these in order — the scraper must populate the DB before the API has anything to serve:

```bash
# Terminal 1 — populate the database (takes ~2 min on first run)
just scrape

# Terminal 2 — start the API
just api

# Terminal 3 — start the frontend
just web
```

Open `http://127.0.0.1:3000`, sign in with Spotify, and click **Sync**. The sync clusters your listening history and takes ~10 seconds. Events with scores appear immediately after.

### 5. Keep events fresh (optional)

```bash
just worker   # starts the APScheduler worker — scrapes nightly at 3am PT
```

Or re-run `just scrape` manually whenever you want fresh data.

## Dev commands

```bash
just api      # FastAPI on :8000 with hot reload
just web      # Next.js on :3000
just scrape   # run ingestion pipeline once
just worker   # start nightly APScheduler worker

just test
just lint
just fmt
```

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
