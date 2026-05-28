from .base import BaseScraper, RawEvent
from .barboza import BarbozaScraper
from .chopsuey import ChopSueyScraper
from .crocodile import CrocodileScraper
from .neumos import NeumosScraper
from .showbox import ShowboxSoDoScraper
from .showbox_market import ShowboxMarketScraper
from .songkick import SongkickScraper
from .stg import STGScraper
from .sunset import SunsetTavernScraper
from .tractor import TractorTavernScraper

# Each scraper runs in isolation — one failure doesn't stop the others.
# Songkick is kept imported but excluded — returns 406 (bot-blocked).
ALL_SCRAPERS: list[type[BaseScraper]] = [
    NeumosScraper,
    CrocodileScraper,
    SunsetTavernScraper,
    ShowboxSoDoScraper,
    ShowboxMarketScraper,
    ChopSueyScraper,
    TractorTavernScraper,
    BarbozaScraper,
    STGScraper,
]

__all__ = ["BaseScraper", "RawEvent", "ALL_SCRAPERS"]
