# Contributing to Concert Finder

## Accounts you need to create

You need accounts on four services to run this locally. All are free.

### 1. Spotify (required — auth + artist data)

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account (create one if you don't have one)
3. Click **Create app**
4. Fill in any name/description; set the redirect URI to `http://127.0.0.1:3000/api/auth/callback/spotify`
5. Copy **Client ID** and **Client Secret** from Settings

> Use `127.0.0.1`, not `localhost` — Spotify's OAuth explicitly blocks `localhost` as a redirect target.

### 2. Last.fm (required — genre tags)

1. Go to [last.fm/api/account/create](https://www.last.fm/api/account/create)
2. Sign up for a Last.fm account if needed
3. Fill in the application form (any name; leave callback URL blank)
4. Copy the **API key** — you don't need the secret

Spotify removed genre data from its API in November 2024. Last.fm crowd-sourced tags fill the gap.

### 3. HuggingFace (required — embeddings + explanations)

1. Go to [huggingface.co](https://huggingface.co) and create an account
2. Go to [Settings → Access Tokens](https://huggingface.co/settings/tokens)
3. Click **New token** → choose **Read** access → copy the token

This is used to download the local embedding model (`BAAI/bge-small-en-v1.5`) without hitting rate limits, and to power the one-sentence match explanations via the free Inference API.

### 4. Ticketmaster (optional — Live Nation venues)

Without this key the scraper silently skips WaMu Theater, Climate Pledge Arena, White River Amphitheatre, and ~60 other Live Nation venues. Everything else still works.

1. Go to [developer.ticketmaster.com](https://developer.ticketmaster.com)
2. Create an account and click **My Apps** → **Create New App**
3. Copy the **Consumer Key** (free tier gives 5,000 API calls/day)

---

## Local setup

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.11+ | [python.org](https://python.org) or your system package manager |
| `uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node 20+ | [nodejs.org](https://nodejs.org) |
| `pnpm` | `npm i -g pnpm` |
| `just` | [just.systems/man/en/packages.html](https://just.systems/man/en/packages.html) |

### 1. Clone and install dependencies

```bash
git clone https://github.com/VineetN/concert-finder
cd concert-finder
just install
```

### 2. Create your env files

```bash
cp .env.example .env
cp apps/web/.env.local.example apps/web/.env.local
```

Fill in `.env` (used by the FastAPI backend, worker, and scrapers):

| Variable | Value |
|----------|-------|
| `SPOTIFY_CLIENT_ID` | From your Spotify app dashboard |
| `SPOTIFY_CLIENT_SECRET` | From your Spotify app dashboard |
| `AUTH_SECRET` | Run `openssl rand -base64 32` and paste the result |
| `LASTFM_API_KEY` | From your Last.fm API account |
| `HF_TOKEN` | From HuggingFace → Settings → Tokens |
| `TICKETMASTER_API_KEY` | From Ticketmaster → My Apps (optional) |

Fill in `apps/web/.env.local` (used by Next.js):

| Variable | Value |
|----------|-------|
| `SPOTIFY_CLIENT_ID` | Same as above |
| `SPOTIFY_CLIENT_SECRET` | Same as above |
| `AUTH_SECRET` | Same value you generated above |
| `NEXTAUTH_SECRET` | Same value again (Auth.js reads both names) |
| `AUTH_URL` | `http://127.0.0.1:3000` — pre-filled in example, don't change |
| `API_URL` | `http://127.0.0.1:8000` — pre-filled in example, don't change |

### 3. Run the first-time setup

Each command goes in its own terminal:

```bash
# Terminal 1 — populate the DB (takes ~2 min on first run)
just scrape

# Terminal 2 — start the API (wait for scrape to finish first)
just api

# Terminal 3 — start the frontend
just web
```

Open `http://127.0.0.1:3000`, sign in with Spotify, and click **Sync**. Sync clusters your listening history (~10 seconds). Events appear immediately after.

### 4. Day-to-day dev commands

```bash
just api      # FastAPI on :8000 with hot reload
just web      # Next.js on :3000
just scrape   # re-run ingestion pipeline
just test     # run all tests
just lint     # ruff + tsc
just fmt      # ruff format
```

---

## Common issues

**Events page stuck loading after restarting the API**
Hard-refresh the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`) — an in-flight request from the old API process will never resolve otherwise.

**`just` not found**
Make sure the `just` binary is on your PATH after installation. On Windows: restart your terminal, or add `~/.cargo/bin` to PATH if you installed via cargo.

**Spotify sign-in fails / redirect mismatch**
Check that `http://127.0.0.1:3000/api/auth/callback/spotify` is listed as an allowed redirect URI in your Spotify app dashboard. The URI must be exact — `localhost` will not work.

**`TICKETMASTER_API_KEY` is set but Ticketmaster scraper returns 0 events**
The key might not be activated yet — Ticketmaster can take a few minutes after app creation.

**Embedding model downloads slowly on first run**
The `BAAI/bge-small-en-v1.5` model (~130 MB) downloads once on first use and is cached. Set your `HF_TOKEN` to avoid anonymous rate limits.

---

## Architecture overview

The codebase is a `uv` workspace with four packages:

```
packages/shared/    — SQLModel DB schemas (Artist, Event, EventArtist, UserSession)
packages/ingest/    — scrapers + Spotify/Last.fm enrichment pipeline
packages/scoring/   — HDBSCAN taste clustering + cosine similarity scoring
apps/api/           — FastAPI backend (events, user sync endpoints)
apps/web/           — Next.js 14 frontend (App Router + Auth.js v5)
```

Scrapers live in `packages/ingest/src/concert_finder_ingest/scrapers/`. Each is a class that implements `scrape() -> list[RawEvent]`. Add the class to `ALL_SCRAPERS` in `scrapers/__init__.py` to include it in the pipeline.

All Python commands should be run with `uv run` rather than `python` directly — this ensures the correct virtualenv is active.
