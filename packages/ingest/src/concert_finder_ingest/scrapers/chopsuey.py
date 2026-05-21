from __future__ import annotations

from .ticketweb import TicketWebScraper


class ChopSueyScraper(TicketWebScraper):
    source_name = "chop_suey"
    venue_slug = "chop-suey"
    venue_id = "19270"
    venue_name = "Chop Suey"
