from .base import BaseScraper, RawEvent
from .neumos import NeumosScraper
from .songkick import SongkickScraper

# Register scrapers here. Each runs in isolation — one failure doesn't stop others.
ALL_SCRAPERS: list[type[BaseScraper]] = [
    SongkickScraper,
    NeumosScraper,
    # Add as built:
    # CrocodileScraper,
    # ShowboxScraper,
    # TractorTavernScraper,
    # SunsetTavernScraper,
    # ChopSueyScraper,
    # BarbozaScraper,
]

__all__ = ["BaseScraper", "RawEvent", "ALL_SCRAPERS"]
