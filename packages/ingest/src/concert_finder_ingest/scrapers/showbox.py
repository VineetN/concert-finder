from __future__ import annotations

from .ticketweb import TicketWebScraper


class ShowboxSoDoScraper(TicketWebScraper):
    source_name = "showbox_sodo"
    venue_slug = "showbox-sodo"
    venue_id = "425085"
    venue_name = "Showbox SoDo"
