from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from sqlmodel import select

from concert_finder_shared.db import get_session
from concert_finder_shared.models import Artist, Event, EventArtist
from concert_finder_scoring.embeddings import build_artist_vector

from .enrichment import SpotifyEnricher
from .scrapers import ALL_SCRAPERS, RawEvent

log = logging.getLogger(__name__)


def run_pipeline(spotify_token: str | None = None) -> None:
    """Full ingestion pass: scrape → deduplicate → enrich → write to DB."""
    log.info("Pipeline started at %s", datetime.now(timezone.utc).isoformat())

    # --- 1. Scrape all venues ---
    parsed: list[tuple[RawEvent, datetime, float | None, float | None]] = []
    all_names: set[str] = set()

    for scraper_cls in ALL_SCRAPERS:
        scraper = scraper_cls()
        try:
            raw_events = scraper.scrape()
            log.info("%s: %d raw events", scraper.source_name, len(raw_events))
            for ev in raw_events:
                date = _parse_date(ev.date_str)
                if date is None:
                    log.warning("Skipping unparseable date %r from %s", ev.date_str, scraper.source_name)
                    continue
                price_min, price_max = _parse_price(ev.price_str)
                parsed.append((ev, date, price_min, price_max))
                all_names.add(ev.headliner)
                all_names.update(ev.openers)
        except Exception:
            log.exception("%s scraper failed — skipping", scraper.source_name)

    log.info("Scraped %d valid events, %d unique artist names", len(parsed), len(all_names))

    # --- 2. Resolve artists (DB lookup + optional Spotify enrichment) ---
    name_to_id = _resolve_artists(all_names, spotify_token)

    # --- 3. Upsert Events + EventArtist links ---
    _upsert_events(parsed, name_to_id)

    log.info("Pipeline complete")


def _resolve_artists(names: set[str], spotify_token: str | None) -> dict[str, str]:
    """
    Ensure every artist in `names` exists in DB.
    Returns {artist_name: artist_id} for all resolved names.

    Strategy:
      1. Bulk-load existing artists by name (one query).
      2. Enrich missing artists via Spotify (or create stubs when unavailable).
      3. Compute embeddings for any artist that lacks one.
      4. Commit; return name → id mapping as plain strings.
    """
    if not names:
        return {}

    enricher = SpotifyEnricher(spotify_token) if spotify_token else None
    try:
        with get_session() as session:
            existing = session.exec(
                select(Artist).where(Artist.name.in_(list(names)))
            ).all()
            known: dict[str, Artist] = {a.name: a for a in existing}
            missing = names - known.keys()
            log.info("Artists: %d in DB, %d to resolve", len(known), len(missing))

            for name in sorted(missing):
                artist: Artist | None = None
                if enricher:
                    try:
                        artist = enricher.enrich_artist(name)
                    except Exception:
                        log.warning("Enrichment failed for %r", name, exc_info=True)
                if artist is None:
                    # Stub: no Spotify data; embedding will be text-only
                    artist = Artist(id=_slugify(name), name=name)
                # Guard: same Spotify ID may already be in DB or added this run
                existing_by_id = session.get(Artist, artist.id)
                if existing_by_id is not None:
                    known[name] = existing_by_id
                    continue
                known[name] = artist
                session.add(artist)

            # Compute embeddings for any artist that doesn't have one yet
            for artist in known.values():
                if artist.embedding is None:
                    try:
                        vec = build_artist_vector(
                            artist.name,
                            json.loads(artist.genres) if artist.genres else [],
                            json.loads(artist.audio_features) if artist.audio_features else None,
                        )
                        artist.embedding = vec.tobytes()
                        session.add(artist)
                    except Exception:
                        log.warning("Embedding failed for %r", artist.name)

            session.commit()
            # Attributes expire on commit; read .id while session is still open
            return {name: a.id for name, a in known.items()}
    finally:
        if enricher:
            enricher.close()


def _upsert_events(
    parsed: list[tuple[RawEvent, datetime, float | None, float | None]],
    name_to_id: dict[str, str],
) -> None:
    """
    Insert new Event rows and EventArtist links; skip duplicates by stable ID.
    Billing order: headliner = 0, openers = 1, 2, …
    """
    with get_session() as session:
        ev_inserted = 0
        link_inserted = 0

        for raw, date, price_min, price_max in parsed:
            event_id = _event_id(date, raw.venue, raw.headliner)

            if session.get(Event, event_id) is None:
                session.add(Event(
                    id=event_id,
                    date=date,
                    venue=raw.venue,
                    ticket_url=raw.ticket_url,
                    price_min=price_min,
                    price_max=price_max,
                    source=raw.source,
                ))
                ev_inserted += 1

            bill = [(raw.headliner, 0)] + [(name, pos + 1) for pos, name in enumerate(raw.openers)]
            for artist_name, billing_pos in bill:
                artist_id = name_to_id.get(artist_name)
                if artist_id is None:
                    continue
                exists = session.exec(
                    select(EventArtist).where(
                        EventArtist.event_id == event_id,
                        EventArtist.artist_id == artist_id,
                    )
                ).first()
                if exists is None:
                    session.add(EventArtist(
                        event_id=event_id,
                        artist_id=artist_id,
                        billing_position=billing_pos,
                    ))
                    link_inserted += 1

        session.commit()
        log.info("Upserted %d events, %d artist-event links", ev_inserted, link_inserted)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_id(date: datetime, venue: str, headliner: str) -> str:
    key = f"{date.date()}|{venue.lower()}|{headliner.lower()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _parse_date(date_str: str) -> datetime | None:
    """Parse ISO 8601 or common venue-site date strings to a naive UTC datetime."""
    s = date_str.strip()
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_price(price_str: str | None) -> tuple[float | None, float | None]:
    """Extract price range from raw strings like '$15', '$15-$25', 'Free'."""
    if not price_str:
        return None, None
    if "free" in price_str.lower():
        return 0.0, 0.0
    nums = [float(m) for m in re.findall(r'\d+(?:\.\d+)?', price_str)]
    if not nums:
        return None, None
    return nums[0], nums[-1] if len(nums) > 1 else None


def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
