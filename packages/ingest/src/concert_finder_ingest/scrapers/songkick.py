from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

SEATTLE_METRO_ID = 3570
_BASE = "https://www.songkick.com"
_LIST_URL = (
    f"{_BASE}/concerts"
    f"?utf8=%E2%9C%93&filters%5Blocation%5D=sk%3A{SEATTLE_METRO_ID}"
)
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_MAX_PAGES = 5


def _today():
    return datetime.now(timezone.utc).date()


def _parse_songkick_date(text: str) -> str | None:
    """Parse 'Fri 12 June' or 'Sun 24 May' → ISO date, inferring year from today."""
    text = text.strip()
    # Prefix a fixed dummy year so strptime never operates without one (avoids
    # the Python 3.15 deprecation for yearless date parsing).
    for fmt in ("%a %d %B", "%a %d %b", "%d %B", "%d %b", "%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(f"2000 {text}", f"%Y {fmt}")
            today = _today()
            candidate = parsed.replace(year=today.year).date()
            if candidate < today:
                candidate = parsed.replace(year=today.year + 1).date()
            return candidate.isoformat()
        except ValueError:
            continue
    return None


def _parse_artists(raw: str) -> tuple[str, list[str]]:
    """Split 'A, B, and C' → headliner='A', openers=['B', 'C']."""
    parts = re.split(r",\s+(?:and\s+)?|\s+and\s+", raw.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return raw.strip(), []
    return parts[0], parts[1:]


class SongkickScraper(BaseScraper):
    source_name = "songkick"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def scrape(self) -> list[RawEvent]:
        if self.api_key:
            return self._scrape_api()
        return self._scrape_web()

    def _scrape_api(self) -> list[RawEvent]:
        raise NotImplementedError("Songkick API scraper not yet implemented")

    def _scrape_web(self) -> list[RawEvent]:
        seen_hrefs: set[str] = set()
        events: list[RawEvent] = []

        with httpx.Client(
            headers={"User-Agent": _UA},
            follow_redirects=True,
            timeout=20,
        ) as client:
            for page in range(1, _MAX_PAGES + 1):
                url = f"{_LIST_URL}&page={page}"
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("Songkick page %d fetch failed: %s", page, exc)
                    break

                tree = HTMLParser(resp.text)
                cards = tree.css("li.event-carousel-card, li.portrait-fixed-list-item")
                if not cards:
                    log.info("Songkick page %d: no cards — stopping pagination", page)
                    break

                page_new = 0
                for card in cards:
                    anchor = card.css_first("a")
                    if anchor is None:
                        continue
                    href = anchor.attributes.get("href", "")
                    if not href or href in seen_hrefs:
                        continue
                    seen_hrefs.add(href)

                    primary = card.css_first(".primary-content")
                    secondary = card.css_first(".secondary-content")
                    tertiary = card.css_first(".tertiary-content")
                    if not (primary and secondary and tertiary):
                        continue

                    date_str = _parse_songkick_date(secondary.text(strip=True))
                    if date_str is None:
                        log.debug("Songkick: unparseable date %r — skipping", secondary.text(strip=True))
                        continue

                    headliner, openers = _parse_artists(primary.text(strip=True))

                    events.append(RawEvent(
                        date_str=date_str,
                        venue=tertiary.text(strip=True),
                        headliner=headliner,
                        openers=openers,
                        ticket_url=f"{_BASE}{href}",
                        price_str=None,
                        source=self.source_name,
                    ))
                    page_new += 1

                log.info("Songkick page %d: %d new events (total %d)", page, page_new, len(events))
                if page > 1 and page_new < 10:
                    break

        log.info("Songkick scrape complete: %d unique events", len(events))
        return events
