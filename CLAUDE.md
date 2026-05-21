# Concert Finder — Claude Code Context

## What this is
A Seattle live music recommender. Scrapes upcoming shows, enriches every artist on
the bill with Spotify metadata + HuggingFace embeddings, clusters the user's listening
history into 2–4 taste modes, and ranks events by predicted enjoyment.
Two categories: **Safe Bets** (strong match to dominant taste) and
**Stretch Picks** (strong match to a secondary taste mode).

Two-node design: Node A runs the scraper worker nightly; Node B serves the API + frontend.
DB is SQLite, synced via Litestream → Cloudflare R2.

## Architecture decisions (already locked in — don't revisit)
- **Python env**: `uv` workspaces. Run everything with `uv run …`, not `python …`.
- **DB**: SQLite + `sqlite-vec`. No Postgres. If we outgrow it, DuckDB is the swap.
- **DB sync**: Litestream → Cloudflare R2. Config at `infra/litestream.yml`.
- **Scheduling**: APScheduler inside `worker/worker.py`. No cron, no Celery.
- **Process manager**: pm2 (`ecosystem.config.js`). Not systemd, not supervisor.
- **Backend**: FastAPI + uvicorn single-process. No gunicorn (not cross-platform).
- **Frontend**: Next.js 14 App Router + Tailwind + Auth.js v5 (next-auth@beta).
- **Embeddings**: `BAAI/bge-small-en-v1.5` via `sentence-transformers` — local, CPU, ~130 MB.
  Do NOT swap this for OpenAI embeddings.
- **"Why this match" explanations**: HuggingFace Inference API (free tier),
  model `Qwen/Qwen2.5-72B-Instruct`. Fallback: local `Qwen/Qwen2.5-1.5B-Instruct`.
  Do NOT use OpenAI API — we explicitly removed it to keep costs at $0.
- **Taste clustering**: HDBSCAN with KMeans(k=3) fallback. Already implemented in
  `packages/scoring/src/concert_finder_scoring/taste.py`.
- **Scoring**: cosine sim × billing weight (1.0 / 0.7 / 0.5). Already implemented in
  `packages/scoring/src/concert_finder_scoring/match.py`.
- **Cold-start audio (v1 skip)**: LAION CLAP (`laion/larger_clap_general`) is the
  planned approach for artists not on Spotify. Out of scope for v1.

## Repo layout
```
concert-finder/
├── apps/api/          FastAPI backend
│   └── src/concert_finder_api/
│       ├── main.py              ← app setup, lifespan, CORS; events router has NO prefix
│       ├── db.py                ← re-exports engine/get_session/init_db from shared
│       └── routers/
│           ├── events.py        ← GET /events, GET /events/taste-map (routes own their paths)
│           └── user.py          ← POST /user/sync
├── apps/web/          Next.js 14 frontend
│   └── src/
│       ├── app/
│       │   ├── page.tsx              ← home (auth-guarded, renders <EventFeed>)
│       │   ├── signin/page.tsx       ← Spotify sign-in button
│       │   └── api/auth/[...nextauth]/route.ts  ← custom Auth handler (127.0.0.1 fix)
│       ├── components/
│       │   ├── EventCard.tsx         ← single event card with chips
│       │   └── EventFeed.tsx         ← tabbed feed: All / Safe Bets / Stretch Picks
│       └── lib/
│           ├── auth-config.ts        ← NextAuth config (Spotify provider, JWT/session callbacks)
│           ├── auth.ts               ← exports handlers/auth/signIn/signOut
│           └── api.ts                ← fetchEvents(), syncUser(), fetchTasteMap()
├── packages/shared/   SQLModel schemas + DB helpers
│   └── src/concert_finder_shared/
│       ├── models.py            ← Artist, Event, EventArtist, UserSession
│       └── db.py                ← engine setup, sqlite-vec extension, init_db, get_session
├── packages/ingest/   Scrapers + Spotify enrichment
│   └── src/concert_finder_ingest/
│       ├── pipeline.py          ← COMPLETE: scrape → resolve_artists → upsert_events
│       ├── enrichment.py        ← SpotifyEnricher: enrich_artist(), get_audio_features()
│       └── scrapers/
│           ├── base.py          ← BaseScraper ABC + RawEvent dataclass
│           ├── songkick.py      ← COMPLETE: web scrape with pagination (API stub kept)
│           ├── neumos.py        ← COMPLETE: selectolax HTML parser
│           └── crocodile.py     ← COMPLETE: JSON-LD schema extraction
├── packages/scoring/  ML: embeddings, clustering, scoring
│   └── src/concert_finder_scoring/
│       ├── embeddings.py        ← build_artist_vector() — COMPLETE
│       ├── taste.py             ← compute_taste_modes() HDBSCAN/KMeans — COMPLETE
│       └── match.py             ← score_event(), EventCategory enum — COMPLETE
└── worker/worker.py   APScheduler; fetches fresh Spotify token before each run
```

## What's COMPLETE vs TODO

### Complete
- Full DB layer (`shared/db.py`, `api/db.py`)
- `POST /user/sync` — fetches top artists (3 time ranges), Last.fm genre enrichment,
  recency-weighted clustering, upserts session
- `GET /events` — resolves user from Bearer token, scores events, parallel HF explanations
- `GET /events/taste-map` — UMAP projection of user's top artists + event headliners;
  `scoring/project.py` (UMAP / PCA fallback); `TasteMap.tsx` Plotly scatter
- Full pipeline (scrape → resolve/enrich artists → embed → upsert events)
- Scoring engine: `match.py`, `taste.py`, `embeddings.py`; calibrated thresholds (0.73/0.70)
- Scrapers: Songkick (web), Neumos, Crocodile — all returning real `RawEvent` objects
- Worker with auto-refreshing Spotify client_credentials token
- Full frontend: signin page, home page, `EventFeed` (tabbed + sync button), `EventCard`,
  `TasteMap` (Plotly scatter with UMAP clusters)
- Auth.js v5 Spotify OAuth with 127.0.0.1 workaround in `route.ts`
- Silent Spotify token refresh in `auth-config.ts` JWT callback

### TODO for v1
1. **More scrapers** — Showbox, Tractor Tavern, Sunset Tavern, etc. are commented out in
   `scrapers/__init__.py`. Run `just scrape` to verify current 3 scrapers hit ≥100 events
   before adding more.
2. **Scraper-discovered artists** — artists ingested via scrapers (not user sync) still use
   old embeddings if `embedding` column was populated before the 50/50 weight change.
   To refresh: `UPDATE artist SET embedding = NULL;` then re-run `just scrape` to
   recompute via the pipeline's `enrich_artist()` path.

## Routing note (don't change this)
`main.py` includes `events.router` with **no prefix**. The routes in `events.py` own
their own paths (`/events`, `/events/taste-map`). The user router uses prefix `/user`,
so its route `/sync` becomes `/user/sync`. Don't add a prefix to the events router.

## Dev commands
```bash
# Install all deps (requires uv + pnpm)
just install

# Run each service
just api        # FastAPI on :8000 with hot reload
just web        # Next.js on :3000
just worker     # APScheduler worker (Node A)
just scrape     # Run pipeline once immediately (for testing)

# Quality
just test
just lint
just fmt
```

## Key env vars (see .env.example)
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — used for both user OAuth AND worker enrichment
- `AUTH_SECRET` — Auth.js v5 session signing key (`openssl rand -base64 32`)
- `AUTH_URL` — full origin for auth callbacks, e.g. `http://127.0.0.1:3000`
- `HF_TOKEN` — HuggingFace token for Inference API (free tier is fine)
- `DATABASE_URL` — path to SQLite file, default `../../data/concert.db`
- `FRONTEND_URL` — for CORS; `http://localhost:3000` in dev

## Scraper guidance
- Use `httpx` + `selectolax` for static HTML. Only reach for `playwright` if a venue
  site absolutely requires JS rendering (none of the current three do).
- Each scraper lives in `packages/ingest/src/concert_finder_ingest/scrapers/`.
  Add the class to `ALL_SCRAPERS` in `scrapers/__init__.py`.
- Scrapers are isolated — one raising an exception doesn't abort the others.
- `RawEvent.date_str` should be ISO 8601 where possible; `pipeline.py` normalizes it.

## Scoring thresholds
- Safe Bet: `sim > 0.73` and matched the **dominant** taste mode
- Stretch Pick: `sim > 0.70` and matched a **non-dominant** taste mode
- Everything else: Regular
- Billing weights: headliner 1.0, direct support 0.7, opener 0.5
