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
- **Frontend**: Next.js 14 App Router + Tailwind + NextAuth v5 beta.
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
│       ├── main.py              ← app setup, lifespan, CORS, router registration
│       └── routers/
│           ├── events.py        ← GET /events, GET /events/taste-map
│           └── user.py          ← POST /user/sync
├── apps/web/          Next.js 14 frontend
│   └── src/
│       ├── app/
│       │   ├── page.tsx         ← home page (guarded by auth)
│       │   └── api/auth/[...nextauth]/route.ts
│       ├── components/EventCard.tsx
│       └── lib/
│           ├── auth.ts          ← NextAuth v5 + Spotify provider
│           └── api.ts           ← fetchEvents(), fetchTasteMap()
├── packages/shared/   SQLModel schemas (Artist, Event, EventArtist, UserSession)
├── packages/ingest/   Scrapers + Spotify enrichment
│   └── src/concert_finder_ingest/
│       ├── pipeline.py          ← orchestrates scrape → enrich → write to DB
│       ├── enrichment.py        ← SpotifyEnricher class (fully written)
│       └── scrapers/
│           ├── base.py          ← BaseScraper ABC + RawEvent dataclass
│           ├── songkick.py      ← stub (API + web fallback, TODO implement)
│           └── neumos.py        ← stub (TODO implement)
├── packages/scoring/  ML: embeddings, clustering, scoring
│   └── src/concert_finder_scoring/
│       ├── embeddings.py        ← build_artist_vector() — COMPLETE
│       ├── taste.py             ← compute_taste_modes() — COMPLETE
│       └── match.py             ← score_event(), EventCategory — COMPLETE
└── worker/worker.py   APScheduler entry point for Node A
```

## What's implemented vs TODO

### COMPLETE (logic written, just needs DB wiring)
- `packages/scoring/` — all three modules are fully functional
- `packages/ingest/enrichment.py` — SpotifyEnricher with audio feature averaging
- `packages/shared/models.py` — all four SQLModel tables
- `apps/web/src/lib/auth.ts` — Spotify OAuth with token persistence
- `apps/web/src/components/EventCard.tsx` — card UI with Safe Bet / Stretch Pick chips
- `apps/api/src/concert_finder_api/routers/` — route signatures + response models

### TODO (in priority order for v1)
1. **DB setup**: Create SQLite + sqlite-vec DB on startup; write `db.py` helper with
   connection management. Both api and worker need this.
2. **`POST /user/sync`** (`routers/user.py`): Call Spotify `/me/top/artists` (all three
   time ranges), enrich missing artists, run `compute_taste_modes()`, upsert UserSession.
3. **`GET /events`** (`routers/events.py`): Load UserSession, score all events, sort,
   generate explanations via HF Inference API, return ranked list.
4. **`pipeline.py`**: Wire the `TODO` blocks — build Event + EventArtist records from
   RawEvent, compute embeddings, upsert everything to DB.
5. **Scrapers** (the bulk of the work — each one is isolated):
   - Songkick web scrape fallback (API key probably unavailable)
   - Neumos, Crocodile, Showbox SoDo, Tractor Tavern, Sunset Tavern
   - KEXP calendar, Barboza, Chop Suey, Madame Lou's
   - Target: ≥100 events in DB at any time
6. **`GET /events/taste-map`**: UMAP projection of user artists + event artists.
   Returns `{user_points, event_points}` for Plotly scatter in the frontend.
7. **Frontend feed**: `EventFeed` component — tabbed Safe Bets / Stretch Picks,
   calls `fetchEvents()`, renders `<EventCard>` list.
8. **Spotify client_credentials token**: Worker needs a service account token
   (not a user OAuth token) for enrichment. Add token refresh logic to `enrichment.py`.

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
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — Spotify app credentials
- `NEXTAUTH_SECRET` — random 32-byte string (`openssl rand -base64 32`)
- `HF_TOKEN` — HuggingFace token for Inference API (free tier is fine)
- `DATABASE_URL` — path to SQLite file, default `../../data/concert.db`
- `FRONTEND_URL` — for CORS; `http://localhost:3000` in dev

## Scraper guidance
- Use `httpx` + `selectolax` for static HTML. Only reach for `playwright` if the
  venue site absolutely requires JS rendering.
- Each scraper lives in `packages/ingest/src/concert_finder_ingest/scrapers/`.
  Add the class to `ALL_SCRAPERS` in `scrapers/__init__.py`.
- Scrapers are isolated — one raising an exception doesn't abort the others.
- `RawEvent.date_str` should be ISO 8601 where possible; `pipeline.py` normalizes.

## Scoring thresholds
- Safe Bet: `sim > 0.75` and matched the **dominant** taste mode
- Stretch Pick: `sim > 0.60` and matched a **non-dominant** taste mode
- Everything else: Regular
- Billing weights: headliner 1.0, direct support 0.7, opener 0.5
