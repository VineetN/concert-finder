"""
Ticketmaster Discovery API scraper — covers all Ticketmaster/Live Nation
venues within 50 miles of Seattle.

This catches venues that are impossible to scrape directly (JS-rendered
Live Nation pages): WaMu Theater, Climate Pledge Arena, White River
Amphitheatre, Chateau Ste. Michelle, and any other TM-ticketed show in
the Seattle metro area.

Requires TICKETMASTER_API_KEY in the environment (free at
developer.ticketmaster.com — 5,000 calls/day on the free tier).
"""
from __future__ import annotations

import logging
import os

import httpx

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_API = "https://app.ticketmaster.com/discovery/v2/events.json"
_SEATTLE_LATLONG = "47.6062,-122.3321"
_RADIUS_MILES = "50"
_PAGE_SIZE = 200


class TicketmasterScraper(BaseScraper):
    source_name = "ticketmaster"

    def scrape(self) -> list[RawEvent]:
        api_key = os.environ.get("TICKETMASTER_API_KEY", "")
        if not api_key:
            log.warning("TICKETMASTER_API_KEY not set — skipping Ticketmaster scraper")
            return []

        events: list[RawEvent] = []
        page = 0

        with httpx.Client(timeout=20) as client:
            while True:
                try:
                    resp = client.get(_API, params={
                        "apikey": api_key,
                        "latlong": _SEATTLE_LATLONG,
                        "radius": _RADIUS_MILES,
                        "unit": "miles",
                        "classificationName": "music",
                        "size": _PAGE_SIZE,
                        "page": page,
                        "sort": "date,asc",
                    })
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("Ticketmaster API error (page %d): %s", page, exc)
                    break

                data = resp.json()
                raw = data.get("_embedded", {}).get("events", [])

                for ev in raw:
                    event = self._parse_event(ev)
                    if event:
                        events.append(event)

                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 1)
                if page >= total_pages - 1:
                    break
                page += 1

        log.info("Ticketmaster scrape complete: %d events", len(events))
        return events

    def _parse_event(self, ev: dict) -> RawEvent | None:
        date_str = ev.get("dates", {}).get("start", {}).get("localDate")
        if not date_str:
            return None

        venues = ev.get("_embedded", {}).get("venues", [])
        venue_name = venues[0].get("name", "").strip() if venues else ""
        if not venue_name:
            return None

        # Attractions are listed in billing order — first is headliner
        attractions = ev.get("_embedded", {}).get("attractions", [])
        if attractions:
            headliner = attractions[0].get("name", "").strip()
            openers = [
                a.get("name", "").strip()
                for a in attractions[1:]
                if a.get("name", "").strip()
            ]
        else:
            # Fall back to the event name (e.g. package deals, festivals)
            headliner = ev.get("name", "").strip()
            openers = []

        if not headliner:
            return None

        price_str = None
        price_ranges = ev.get("priceRanges", [])
        if price_ranges:
            p = price_ranges[0]
            mn, mx = p.get("min"), p.get("max")
            if mn is not None and mx is not None and mn != mx:
                price_str = f"${mn:.0f}-${mx:.0f}"
            elif mn is not None:
                price_str = f"${mn:.0f}"

        return RawEvent(
            date_str=date_str,
            venue=venue_name,
            headliner=headliner,
            openers=openers,
            ticket_url=ev.get("url"),
            price_str=price_str,
            source=self.source_name,
        )
