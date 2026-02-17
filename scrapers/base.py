"""Base scraper with shared functionality: rate limiting, robots.txt, async HTTP."""

from __future__ import annotations

import asyncio
import json
import os
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

DATA_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
USER_AGENT = "NovigSiteScraper/1.0 (+https://novig.com)"


class BaseScraper(ABC):
    """Abstract base class for all site scrapers."""

    site_name: str = ""
    base_url: str = ""
    min_delay: float = 1.0
    max_delay: float = 2.0

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._robot_parser: RobotFileParser | None = None
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.teardown()

    async def setup(self):
        """Initialise the HTTP client and load robots.txt."""
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        )
        await self._load_robots_txt()

    async def teardown(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Robots.txt
    # ------------------------------------------------------------------

    async def _load_robots_txt(self):
        """Fetch and parse the site's robots.txt."""
        robots_url = f"{self.base_url}/robots.txt"
        self._robot_parser = RobotFileParser()
        try:
            resp = await self._client.get(robots_url)
            if resp.status_code == 200:
                self._robot_parser.parse(resp.text.splitlines())
            else:
                # If no robots.txt, allow everything
                self._robot_parser.parse([])
        except httpx.HTTPError:
            self._robot_parser.parse([])

    def can_fetch(self, url: str) -> bool:
        """Check whether the URL is allowed by robots.txt."""
        if self._robot_parser is None:
            return True
        return self._robot_parser.can_fetch(USER_AGENT, url)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _rate_limit(self):
        """Wait between requests to be a good citizen."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        delay = random.uniform(self.min_delay, self.max_delay)
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def fetch(self, url: str) -> httpx.Response:
        """Fetch a URL with rate limiting and robots.txt checks.

        Raises ValueError if the URL is disallowed by robots.txt.
        """
        if not self.can_fetch(url):
            raise ValueError(f"URL disallowed by robots.txt: {url}")
        await self._rate_limit()
        response = await self._client.get(url)
        response.raise_for_status()
        return response

    async def fetch_with_playwright(self, url: str) -> str:
        """Render a JS-heavy page with Playwright and return the HTML.

        Raises ValueError if the URL is disallowed by robots.txt.
        """
        if not self.can_fetch(url):
            raise ValueError(f"URL disallowed by robots.txt: {url}")
        await self._rate_limit()
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.goto(url, wait_until="networkidle")
            html = await page.content()
            await browser.close()
        return html

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def output_dir(self) -> Path:
        """Return (and create) the raw data directory for this site."""
        d = DATA_RAW_DIR / self.site_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, articles: list[dict]) -> Path:
        """Save scraped articles as a dated JSON file, return the path."""
        now = datetime.now(timezone.utc)
        payload = {
            "source": self.site_name,
            "scraped_at": now.isoformat(),
            "articles": articles,
        }
        date_str = now.strftime("%Y-%m-%d")
        out_path = self.output_dir() / f"{date_str}.json"
        with open(out_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        return out_path

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def scrape(self) -> list[dict]:
        """Scrape the site and return a list of article dicts.

        Each dict should contain at minimum:
            title, url, content, category, sport
        Optionally: odds_data, raw_html
        """
        ...

    async def run(self) -> Path:
        """Full lifecycle: setup, scrape, save, teardown."""
        async with self:
            articles = await self.scrape()
            path = self.save(articles)
            print(f"[{self.site_name}] Saved {len(articles)} articles to {path}")
            return path
