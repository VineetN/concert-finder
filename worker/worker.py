"""Ingestion worker — schedules the nightly scrape + enrichment pipeline."""
from __future__ import annotations

import argparse
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


def _fetch_client_token() -> str | None:
    """
    Fetch a fresh Spotify client_credentials token.

    Called immediately before every pipeline run — never cached — so the
    token is always valid. (Spotify tokens expire after 1 h; the worker
    process may run for weeks.)

    Returns None if credentials are missing; the pipeline will still run
    but enrichment will be skipped and artists will be stored as stubs.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        log.warning(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not set — "
            "enrichment disabled for this run"
        )
        return None

    try:
        resp = httpx.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        log.info("Spotify client token obtained (valid for ~1 h)")
        return token
    except Exception:
        log.exception(
            "Failed to obtain Spotify client token — enrichment disabled for this run"
        )
        return None


def _run() -> None:
    """Fetch a fresh token, then execute the full pipeline."""
    from concert_finder_ingest.pipeline import run_pipeline
    run_pipeline(spotify_token=_fetch_client_token())


def main() -> None:
    parser = argparse.ArgumentParser(description="Concert Finder ingestion worker")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline once immediately, then exit (useful for testing)",
    )
    args = parser.parse_args()

    if args.run_now:
        log.info("--run-now: executing pipeline immediately")
        _run()
        return

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="America/Los_Angeles")
    scheduler.add_job(
        _run,
        trigger="cron",
        hour=3,
        minute=0,
        id="nightly_pipeline",
        misfire_grace_time=3600,   # retry up to 1h late if machine was asleep
    )
    log.info("Worker started — nightly pipeline scheduled at 03:00 PT")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker stopped")


if __name__ == "__main__":
    main()
