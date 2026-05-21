from __future__ import annotations

import logging

import httpx
from selectolax.parser import HTMLParser

from .base import BaseScraper, RawEvent

log = logging.getLogger(__name__)

URL = "https://www.neumos.com/events"


class NeumosScraper(BaseScraper):
    source_name = "neumos"

    def scrape(self) -> list[RawEvent]:
        # TODO: implement — parse Neumos event listing page
        # Each event block typically contains: date, artist name(s), ticket link
        log.warning("Neumos scraper not yet implemented — returning []")
        return []
