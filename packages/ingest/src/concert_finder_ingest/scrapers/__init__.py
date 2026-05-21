from .base import BaseScraper, RawEvent
from .crocodile import CrocodileScraper
from .neumos import NeumosScraper
from .songkick import SongkickScraper

# Register scrapers here. Each runs in isolation — one failure doesn't stop others.
ALL_SCRAPERS: list[type[BaseScraper]] = [
    SongkickScraper,
    NeumosScraper,
    CrocodileScraper,
    # Add as built:
    # ShowboxScraper,
    # TractorTavernScraper,
    # SunsetTavernScraper,
    # ChopSueyScraper,
    # BarbozaScraper,
]

__all__ = ["BaseScraper", "RawEvent", "ALL_SCRAPERS"]
