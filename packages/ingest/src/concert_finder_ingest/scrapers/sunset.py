from __future__ import annotations

from .ticketweb import TicketWebScraper


class SunsetTavernScraper(TicketWebScraper):
    source_name = "sunset_tavern"
    venue_slug = "sunset-tavern"
    venue_id = "18979"
    venue_name = "Sunset Tavern"
