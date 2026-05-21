from __future__ import annotations

import logging

import httpx

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

SEATTLE_METRO_ID = 3570  # Songkick metro area ID for Seattle


class SongkickScraper(BaseScraper):
    source_name = "songkick"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def scrape(self) -> list[RawEvent]:
        if self.api_key:
            return self._scrape_api()
        return self._scrape_web()

    def _scrape_api(self) -> list[RawEvent]:
        # GET https://api.songkick.com/api/3.0/metro_areas/{id}/calendar.json?apikey={key}&page={n}
        # TODO: paginate through results and map to RawEvent
        raise NotImplementedError("Songkick API scraper not yet implemented")

    def _scrape_web(self) -> list[RawEvent]:
        # Fallback: scrape https://www.songkick.com/metro-areas/3570-us-seattle
        # TODO: parse event cards from the HTML response
        log.warning("Songkick web scraper not yet implemented — returning []")
        return []
