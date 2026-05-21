from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_URL = "https://tractortavern.com/calendar/"
_VENUE = "Tractor Tavern"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _parse_tractor_date(text: str) -> str | None:
    """Parse 'May 21 @ 08:00 PM' → ISO date, handling year rollover."""
    date_part = text.split("@")[0].strip()
    now = datetime.now()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            dt = datetime.strptime(f"{date_part} {now.year}", fmt)
            if dt.date() < now.date() - timedelta(days=1):
                dt = dt.replace(year=dt.year + 1)
            return dt.date().isoformat()
        except ValueError:
            continue
    return None


def _split_artists(name: str) -> tuple[str, list[str]]:
    """
    Split 'Headliner, Support 1, Support 2' into (headliner, [openers]).
    Tractor Tavern lists all artists comma-separated in a single title field.
    """
    parts = [p.strip() for p in name.split(",") if p.strip()]
    return parts[0], parts[1:]


class TractorTavernScraper(BaseScraper):
    source_name = "tractor_tavern"

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
            log.warning("Tractor Tavern fetch failed: %s", exc)
            return []

        tree = HTMLParser(resp.text)
        events: list[RawEvent] = []

        for item in tree.css("div.flexmedia--artistevents"):
            name_el = item.css_first("span.artisteventsname")
            if not name_el:
                continue
            full_name = name_el.text(strip=True)
            if not full_name:
                continue

            time_el = item.css_first("span.artisteventstime")
            if not time_el:
                continue
            date_str = _parse_tractor_date(time_el.text(strip=True))
            if not date_str:
                log.debug("Tractor: unparseable date on %r — skipping", full_name)
                continue

            ticket_a = item.css_first("a.background-wrapper")
            ticket_url = ticket_a.attributes.get("href") if ticket_a else None

            price_el = item.css_first("span.artistseventsprice")
            price_str = price_el.text(strip=True) if price_el else None

            headliner, openers = _split_artists(full_name)

            events.append(RawEvent(
                date_str=date_str,
                venue=_VENUE,
                headliner=headliner,
                openers=openers,
                ticket_url=ticket_url,
                price_str=price_str,
                source=self.source_name,
            ))

        log.info("Tractor Tavern scrape complete: %d events", len(events))
        return events
