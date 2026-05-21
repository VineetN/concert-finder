from .base import BaseScraper, RawEvent
from .barboza import BarbozaScraper
from .chopsuey import ChopSueyScraper
from .crocodile import CrocodileScraper
from .neumos import NeumosScraper
from .showbox import ShowboxSoDoScraper
from .songkick import SongkickScraper
from .sunset import SunsetTavernScraper
from .tractor import TractorTavernScraper

# Each scraper runs in isolation — one failure doesn't stop the others.
ALL_SCRAPERS: list[type[BaseScraper]] = [
    SongkickScraper,
    NeumosScraper,
    CrocodileScraper,
    SunsetTavernScraper,
    ShowboxSoDoScraper,
    ChopSueyScraper,
    TractorTavernScraper,
    BarbozaScraper,
]

__all__ = ["BaseScraper", "RawEvent", "ALL_SCRAPERS"]
