from __future__ import annotations

import json
import logging
import re
from html import unescape

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_TICKETWEB_URL = "https://www.ticketweb.com/venue/the-crocodile-seattle-wa/10352"
_VENUE = "The Crocodile"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _extract_jsonld(html: str) -> list[dict]:
    """Return the schema.org MusicEvent JSON-LD array embedded in the page."""
    tree = HTMLParser(html)
    for script in tree.css("script"):
        text = (script.text() or "").strip()
        if text.startswith("[") and '"MusicEvent"' in text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                log.warning("Crocodile: failed to parse JSON-LD block")
    return []


class CrocodileScraper(BaseScraper):
    source_name = "crocodile"

    def scrape(self) -> list[RawEvent]:
        try:
            resp = httpx.get(
                _TICKETWEB_URL,
                headers={"User-Agent": _UA},
                follow_redirects=True,
                timeout=20,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Crocodile/TicketWeb fetch failed: %s", exc)
            return []

        raw_events = _extract_jsonld(resp.text)
        if not raw_events:
            log.warning("Crocodile: no JSON-LD events found on page")
            return []

        events: list[RawEvent] = []
        for ev in raw_events:
            if ev.get("@type") != "MusicEvent":
                continue

            # startDate is ISO 8601 with time — truncate to date
            start = ev.get("startDate", "")
            date_str = start[:10] if start else None
            if not date_str:
                continue

            performers = ev.get("performer") or []
            if not performers:
                log.debug("Crocodile: no performers for %r — skipping", ev.get("name"))
                continue

            headliner = unescape(performers[0].get("name", "")).strip()
            openers = [unescape(p.get("name", "")).strip() for p in performers[1:] if p.get("name")]

            ticket_url = ev.get("url") or (ev.get("offers") or {}).get("url")

            events.append(RawEvent(
                date_str=date_str,
                venue=_VENUE,
                headliner=headliner,
                openers=openers,
                ticket_url=ticket_url,
                price_str=None,
                source=self.source_name,
            ))

        log.info("Crocodile scrape complete: %d events", len(events))
        return events
