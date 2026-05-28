"""
Showbox Market scraper — The Showbox (downtown Seattle).

showboxpresents.com/events/ lists all Showbox Presents shows across
multiple venues. We filter to "The Showbox" only (Showbox SoDo is
already covered by the TicketWeb scraper).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

_URL = "https://www.showboxpresents.com/events/"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_DATE_RE = re.compile(r"([A-Za-z]+,\s+[A-Za-z]+\s+\d+,\s+\d{4})")


def _parse_date(time_text: str) -> str | None:
    m = _DATE_RE.search(time_text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%a, %B %d, %Y").date().isoformat()
    except ValueError:
        return None


def _parse_openers(h4_text: str) -> list[str]:
    text = re.sub(r"^with\s+", "", h4_text.strip(), flags=re.IGNORECASE)
    if not text:
        return []
    return [p.strip() for p in re.split(r",\s*", text) if p.strip()]


class ShowboxMarketScraper(BaseScraper):
    source_name = "showbox_market"

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
            log.warning("Showbox Market fetch failed: %s", exc)
            return []

        tree = HTMLParser(resp.text)
        events: list[RawEvent] = []
        today = datetime.now(timezone.utc).date()

        for entry in tree.css("div.entry"):
            # Venue filter — skip anything not at The Showbox (downtown)
            venue_el = entry.css_first("span.venue")
            if venue_el is None:
                continue
            if "The Showbox" not in venue_el.text(strip=True):
                continue

            date_el = entry.css_first("span.date")
            if date_el is None:
                continue
            date_str = _parse_date(date_el.text(strip=True))
            if date_str is None:
                continue
            # Skip past events
            try:
                if datetime.fromisoformat(date_str).date() < today:
                    continue
            except ValueError:
                continue

            # Headliner is in h3 > a inside .title
            title_el = entry.css_first(".title")
            if title_el is None:
                continue
            headliner_el = title_el.css_first("h3 a")
            if headliner_el is None:
                continue
            headliner = headliner_el.text(strip=True)
            if not headliner:
                continue

            # Openers in h4 ("with Artist1, Artist2")
            h4 = title_el.css_first("h4")
            openers = _parse_openers(h4.text(strip=True)) if h4 else []

            # Ticket URL from Buy Tickets button (AXS link), fallback to detail page
            ticket_el = entry.css_first("a.btn-tickets")
            ticket_url = (ticket_el.attributes.get("href") if ticket_el else None) or headliner_el.attributes.get("href")

            events.append(RawEvent(
                date_str=date_str,
                venue="The Showbox",
                headliner=headliner,
                openers=openers,
                ticket_url=ticket_url,
                price_str=None,
                source=self.source_name,
            ))

        log.info("Showbox Market scrape complete: %d events", len(events))
        return events
