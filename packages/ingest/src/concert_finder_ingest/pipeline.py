from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from concert_finder_shared.models import Artist, Event, EventArtist

from .enrichment import SpotifyEnricher
from .scrapers import ALL_SCRAPERS

log = logging.getLogger(__name__)


def run_pipeline(spotify_token: str | None = None) -> None:
    """Full ingestion pass: scrape → deduplicate → enrich → write to DB."""
    log.info("Pipeline started at %s", datetime.now(timezone.utc).isoformat())

    raw_artist_names: set[str] = set()

    for scraper_cls in ALL_SCRAPERS:
        scraper = scraper_cls()
        try:
            raw_events = scraper.scrape()
            log.info("%s: %d events", scraper.source_name, len(raw_events))
            for e in raw_events:
                raw_artist_names.add(e.headliner)
                raw_artist_names.update(e.openers)
                # TODO: build Event + EventArtist records and upsert to DB
        except Exception:
            log.exception("%s scraper failed", scraper.source_name)

    log.info("Unique artists to enrich: %d", len(raw_artist_names))

    if spotify_token and raw_artist_names:
        enricher = SpotifyEnricher(spotify_token)
        try:
            for name in sorted(raw_artist_names):
                try:
                    artist = enricher.enrich_artist(name)
                    if artist:
                        # TODO: upsert artist + compute embedding via scoring package
                        log.debug("Enriched %r", name)
                except Exception:
                    log.warning("Failed to enrich %r", name, exc_info=True)
        finally:
            enricher.close()

    log.info("Pipeline complete")


def _event_id(date: datetime, venue: str, headliner: str) -> str:
    key = f"{date.date()}|{venue.lower()}|{headliner.lower()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]
