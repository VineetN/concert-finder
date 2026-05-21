"""
Shared base for TicketWeb venue-page scrapers.

TicketWeb embeds a schema.org MusicEvent JSON-LD array in every venue
listing page. Subclass this, set venue_id / venue_name / source_name,
and get a working scraper for free.
"""
from __future__ import annotations

import json
import logging
from html import unescape

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _extract_jsonld(html: str) -> list[dict]:
    tree = HTMLParser(html)
    for script in tree.css("script"):
        text = (script.text() or "").strip()
        if text.startswith("[") and '"MusicEvent"' in text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                log.warning("TicketWeb: failed to parse JSON-LD block")
    return []


class TicketWebScraper(BaseScraper):
    """Scrapes a TicketWeb venue page using its embedded JSON-LD."""

    venue_id: str = ""    # numeric venue ID from the TicketWeb URL
    venue_slug: str = "" # hyphenated slug used in the TicketWeb URL path
    venue_name: str = "" # display name used in RawEvent.venue

    def scrape(self) -> list[RawEvent]:
        url = f"https://www.ticketweb.com/venue/{self.venue_slug}-seattle-wa/{self.venue_id}"
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": _UA},
                follow_redirects=True,
                timeout=20,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("%s fetch failed: %s", self.venue_name, exc)
            return []

        raw_events = _extract_jsonld(resp.text)
        if not raw_events:
            log.warning("%s: no JSON-LD events on page", self.venue_name)
            return []

        events: list[RawEvent] = []
        for ev in raw_events:
            if ev.get("@type") != "MusicEvent":
                continue
            start = ev.get("startDate", "")
            date_str = start[:10] if start else None
            if not date_str:
                continue

            performers = ev.get("performer") or []
            if not performers:
                continue

            headliner = unescape(performers[0].get("name", "")).strip()
            openers = [
                unescape(p.get("name", "")).strip()
                for p in performers[1:]
                if p.get("name")
            ]

            ticket_url = ev.get("url") or (ev.get("offers") or {}).get("url")

            events.append(RawEvent(
                date_str=date_str,
                venue=self.venue_name,
                headliner=headliner,
                openers=openers,
                ticket_url=ticket_url,
                source=self.source_name,
            ))

        log.info("%s scrape complete: %d events", self.venue_name, len(events))
        return events
