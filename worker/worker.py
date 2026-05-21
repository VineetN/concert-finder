"""Ingestion worker — schedules the nightly scrape + enrichment pipeline."""
from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Concert Finder ingestion worker")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run the pipeline once immediately, then exit (useful for testing)",
    )
    args = parser.parse_args()

    from concert_finder_ingest.pipeline import run_pipeline

    # Service-account token used for artist enrichment (not a user OAuth token).
    # Obtain via client_credentials flow: POST https://accounts.spotify.com/api/token
    spotify_token = os.getenv("SPOTIFY_CLIENT_TOKEN")

    if args.run_now:
        log.info("--run-now: executing pipeline immediately")
        run_pipeline(spotify_token=spotify_token)
        return

    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler(timezone="America/Los_Angeles")
    scheduler.add_job(
        run_pipeline,
        trigger="cron",
        hour=3,
        minute=0,
        kwargs={"spotify_token": spotify_token},
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
