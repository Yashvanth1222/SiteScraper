"""Site scrapers for the SiteScraper content pipeline."""

from __future__ import annotations

from scrapers.base import BaseScraper
from scrapers.bettingpros import BettingProsScraper
from scrapers.covers import CoversScraper
from scrapers.oddsshark import OddsSharkScraper
from scrapers.rotowire import RotoWireScraper

__all__ = [
    "BaseScraper",
    "RotoWireScraper",
    "BettingProsScraper",
    "OddsSharkScraper",
    "CoversScraper",
]
