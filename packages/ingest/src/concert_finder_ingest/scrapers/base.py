from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawEvent:
    date_str: str          # ISO 8601 preferred; parser normalizes
    venue: str
    headliner: str
    openers: list[str] = field(default_factory=list)
    ticket_url: str | None = None
    price_str: str | None = None   # raw string e.g. "$15-$25" — normalized downstream
    source: str = ""


class BaseScraper(ABC):
    requires_js: bool = False   # set True to gate on playwright install
    source_name: str = ""

    @abstractmethod
    def scrape(self) -> list[RawEvent]:
        """Return raw events for the next 60 days.

        Raise on hard failure; return [] when the page is simply empty.
        Each scraper is isolated — one failing doesn't abort the others.
        """
        ...
