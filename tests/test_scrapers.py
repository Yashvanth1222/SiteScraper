"""Tests for the scraper modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from scrapers.base import BaseScraper
from scrapers.rotowire import RotoWireScraper
from scrapers.bettingpros import BettingProsScraper
from scrapers.oddsshark import OddsSharkScraper
from scrapers.covers import CoversScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<html>
<head><title>NBA Best Bets Today</title></head>
<body>
<main>
  <div class="betting-pick">
    <h3 class="pick-title">Lakers -3.5 vs Celtics</h3>
    <span class="odds">-110</span>
    <p>The Lakers are 7-3 in their last 10 games.</p>
    <a href="/betting/nba/lakers-celtics">Full analysis</a>
  </div>
  <div class="betting-pick">
    <h3 class="pick-title">Warriors ML vs Nuggets</h3>
    <span class="odds">+150</span>
    <p>Warriors playing at home with full roster.</p>
  </div>
</main>
</body>
</html>
"""

COVERS_LIST_HTML = """
<html>
<head><title>NBA Betting News</title></head>
<body>
<main>
  <article class="article-card">
    <h2 class="headline">Today's Best NBA Bets</h2>
    <p>Our experts break down the top picks.</p>
    <a href="/nba/betting-news/todays-best-bets">Read more</a>
  </article>
  <article class="article-card">
    <h2 class="headline">Line Movement Report</h2>
    <p>Key line changes for tonight.</p>
    <a href="/nba/betting-news/line-movement">Read more</a>
  </article>
</main>
</body>
</html>
"""

ROBOTS_TXT = "User-agent: *\nDisallow: /admin/\n"

ROBOTS_TXT_BLOCK_ALL = "User-agent: *\nDisallow: /\n"


# ---------------------------------------------------------------------------
# BaseScraper tests
# ---------------------------------------------------------------------------

class ConcreteScraper(BaseScraper):
    """Minimal concrete implementation for testing the base class."""
    site_name = "test_site"
    base_url = "https://example.com"

    async def scrape(self) -> list[dict]:
        return [{"title": "test", "url": "https://example.com/test", "content": "hello"}]


class TestBaseScraper:
    """Tests for the abstract BaseScraper class."""

    @pytest.mark.asyncio
    async def test_setup_and_teardown(self):
        scraper = ConcreteScraper()
        assert scraper._client is None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ROBOTS_TXT

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response):
            await scraper.setup()
            assert scraper._client is not None

        await scraper.teardown()
        assert scraper._client is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ROBOTS_TXT

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response):
            async with ConcreteScraper() as scraper:
                assert scraper._client is not None
            assert scraper._client is None

    @pytest.mark.asyncio
    async def test_can_fetch_allowed(self):
        scraper = ConcreteScraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ROBOTS_TXT

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response):
            await scraper.setup()

        assert scraper.can_fetch("https://example.com/articles")
        assert not scraper.can_fetch("https://example.com/admin/settings")
        await scraper.teardown()

    @pytest.mark.asyncio
    async def test_fetch_disallowed_url_raises(self):
        scraper = ConcreteScraper()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ROBOTS_TXT_BLOCK_ALL

        with patch.object(httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response):
            await scraper.setup()

        with pytest.raises(ValueError, match="disallowed by robots.txt"):
            await scraper.fetch("https://example.com/anything")

        await scraper.teardown()

    def test_save_creates_json(self, tmp_path):
        scraper = ConcreteScraper()
        # Override output dir to use tmp
        scraper.output_dir = lambda: tmp_path

        articles = [{"title": "Test Article", "content": "Body text"}]
        path = scraper.save(articles)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["source"] == "test_site"
        assert len(data["articles"]) == 1
        assert data["articles"][0]["title"] == "Test Article"

    def test_sport_from_path(self):
        assert RotoWireScraper._sport_from_path("/betting/nba/best-bets") == "NBA"
        assert RotoWireScraper._sport_from_path("/betting/ncaab/best-bets") == "NCAAB"
        assert RotoWireScraper._sport_from_path("/betting/nfl/best-bets") == "NFL"
        assert RotoWireScraper._sport_from_path("/random/path") == "UNKNOWN"


# ---------------------------------------------------------------------------
# RotoWire scraper tests
# ---------------------------------------------------------------------------

class TestRotoWireScraper:

    @pytest.mark.asyncio
    async def test_parse_page_with_picks(self):
        from bs4 import BeautifulSoup
        scraper = RotoWireScraper()
        soup = BeautifulSoup(SAMPLE_HTML, "lxml")

        results = scraper._parse_page(soup, "https://www.rotowire.com/betting/nba/best-bets", "/betting/nba/best-bets")

        assert len(results) == 2
        assert results[0]["title"] == "Lakers -3.5 vs Celtics"
        assert results[0]["sport"] == "NBA"
        assert results[0]["category"] == "best_bets"
        assert results[0]["odds_data"]["display"] == "-110"
        assert "rotowire.com" in results[0]["url"]

        assert results[1]["title"] == "Warriors ML vs Nuggets"
        assert results[1]["odds_data"]["display"] == "+150"

    @pytest.mark.asyncio
    async def test_parse_page_fallback_no_cards(self):
        from bs4 import BeautifulSoup
        html = "<html><head><title>Test Page</title></head><body><main><p>Some content</p></main></body></html>"
        scraper = RotoWireScraper()
        soup = BeautifulSoup(html, "lxml")

        results = scraper._parse_page(soup, "https://www.rotowire.com/betting/nba/best-bets", "/betting/nba/best-bets")

        assert len(results) == 1
        assert results[0]["title"] == "Test Page"
        assert "Some content" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_full_scrape_mocked(self):
        scraper = RotoWireScraper()
        scraper.min_delay = 0.0
        scraper.max_delay = 0.0

        mock_robots = MagicMock()
        mock_robots.status_code = 200
        mock_robots.text = ROBOTS_TXT

        mock_page = MagicMock()
        mock_page.status_code = 200
        mock_page.text = SAMPLE_HTML

        async def mock_get(url, **kwargs):
            if "robots.txt" in url:
                return mock_robots
            return mock_page

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch.object(httpx.Response, "raise_for_status"):
                async with scraper:
                    articles = await scraper.scrape()

        assert len(articles) > 0


# ---------------------------------------------------------------------------
# Covers scraper tests
# ---------------------------------------------------------------------------

class TestCoversScraper:

    @pytest.mark.asyncio
    async def test_parse_page_with_articles(self):
        from bs4 import BeautifulSoup
        scraper = CoversScraper()
        soup = BeautifulSoup(COVERS_LIST_HTML, "lxml")

        results = scraper._parse_page(soup, "https://www.covers.com/nba/betting-news", "/nba/betting-news")

        assert len(results) == 2
        assert results[0]["title"] == "Today's Best NBA Bets"
        assert results[0]["sport"] == "NBA"
        assert results[0]["category"] == "best_bets"
        assert "covers.com" in results[0]["url"]


# ---------------------------------------------------------------------------
# Import / instantiation smoke tests
# ---------------------------------------------------------------------------

class TestImports:
    def test_all_scrapers_importable(self):
        from scrapers import (
            BaseScraper,
            RotoWireScraper,
            BettingProsScraper,
            OddsSharkScraper,
            CoversScraper,
        )
        assert issubclass(RotoWireScraper, BaseScraper)
        assert issubclass(BettingProsScraper, BaseScraper)
        assert issubclass(OddsSharkScraper, BaseScraper)
        assert issubclass(CoversScraper, BaseScraper)

    def test_scraper_site_names(self):
        assert RotoWireScraper.site_name == "rotowire"
        assert BettingProsScraper.site_name == "bettingpros"
        assert OddsSharkScraper.site_name == "oddsshark"
        assert CoversScraper.site_name == "covers"

    def test_scraper_base_urls(self):
        assert "rotowire.com" in RotoWireScraper.base_url
        assert "bettingpros.com" in BettingProsScraper.base_url
        assert "oddsshark.com" in OddsSharkScraper.base_url
        assert "covers.com" in CoversScraper.base_url
