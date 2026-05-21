from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_BASE = "https://www.neumos.com"
_EVENTS_URL = f"{_BASE}/events"
_VENUE = "Neumos"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _parse_neumos_date(text: str) -> str | None:
    """Parse 'May 20 2026' (from aria-label) → ISO date string."""
    text = text.strip()
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_openers(tagline: str) -> list[str]:
    """Parse 'with Snowing + Awakebutstillinbed' → ['Snowing', 'Awakebutstillinbed']."""
    tagline = re.sub(r"^with\s+", "", tagline.strip(), flags=re.I)
    parts = re.split(r"\s*\+\s*|\s*,\s*", tagline)
    return [p.strip() for p in parts if p.strip()]


class NeumosScraper(BaseScraper):
    source_name = "neumos"

    def scrape(self) -> list[RawEvent]:
        try:
            resp = httpx.get(
                _EVENTS_URL,
                headers={"User-Agent": _UA},
                follow_redirects=True,
                timeout=20,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("Neumos fetch failed: %s", exc)
            return []

        tree = HTMLParser(resp.text)
        events: list[RawEvent] = []

        for item in tree.css("div.eventItem"):
            ticket_btn = item.css_first("a.tickets")
            if ticket_btn and ticket_btn.attributes.get("data-canceled") == "true":
                continue

            title_a = item.css_first("h3.title a")
            if not title_a:
                continue
            headliner = title_a.text(strip=True)

            date_div = item.css_first(".date")
            if not date_div:
                continue
            date_str = _parse_neumos_date(date_div.attributes.get("aria-label", ""))
            if not date_str:
                log.debug("Neumos: unparseable date on %r — skipping", headliner)
                continue

            tagline = item.css_first("h4.tagline")
            openers = _parse_openers(tagline.text(strip=True)) if tagline else []

            thumb_a = item.css_first("div.thumb a")
            href = thumb_a.attributes.get("href", "") if thumb_a else ""
            ticket_url = f"{_BASE}{href}" if href.startswith("/") else href or None

            events.append(RawEvent(
                date_str=date_str,
                venue=_VENUE,
                headliner=headliner,
                openers=openers,
                ticket_url=ticket_url,
                price_str=None,
                source=self.source_name,
            ))

        log.info("Neumos scrape complete: %d events", len(events))
        return events
