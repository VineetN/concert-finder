"""
Seattle Theatre Group scraper — covers Neptune, Paramount, and Moore.

stgpresents.org embeds one schema.org/Event JSON-LD block per show.
Performer data is always empty, but the `name` field reliably holds the
headliner. Events are filtered to music venues only.
"""
from __future__ import annotations

import json
import logging
import re

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_URL = "https://www.stgpresents.org/calendar"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MUSIC_VENUES = {
    "The Neptune Theatre",
    "The Paramount Theatre",
    "The Moore Theatre",
}
# Strip common "An Evening With …" prefixes that break Spotify search
_PREFIX = re.compile(r"^(?:an evening with|a night with|an afternoon with)\s+", re.IGNORECASE)


def _clean_name(name: str) -> str:
    return _PREFIX.sub("", name).strip()


class STGScraper(BaseScraper):
    source_name = "stg"

    def scrape(self) -> list[RawEvent]:
        try:
            resp = httpx.get(
                _URL,
                headers={"User-Agent": _UA},
                follow_redirects=True,
                timeout=20,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("STG fetch failed: %s", exc)
            return []

        tree = HTMLParser(resp.text)
        events: list[RawEvent] = []

        for script in tree.css('script[type="application/ld+json"]'):
            text = (script.text() or "").strip()
            if not text:
                continue
            try:
                d = json.loads(text)
            except json.JSONDecodeError:
                continue

            venue_name = d.get("location", {}).get("name", "")
            if venue_name not in _MUSIC_VENUES:
                continue

            raw_name = (d.get("name") or "").strip()
            if not raw_name:
                continue

            start = d.get("startDate", "")
            date_str = start[:10] if start else None
            if not date_str:
                continue

            headliner = _clean_name(raw_name)
            ticket_url = d.get("url") or (d.get("offers") or {}).get("url")

            events.append(RawEvent(
                date_str=date_str,
                venue=venue_name,
                headliner=headliner,
                openers=[],
                ticket_url=ticket_url,
                price_str=None,
                source=self.source_name,
            ))

        log.info("STG scrape complete: %d events across Neptune/Paramount/Moore", len(events))
        return events
