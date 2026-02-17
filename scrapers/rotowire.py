"""RotoWire scraper — daily picks, player props, expert analysis."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class RotoWireScraper(BaseScraper):
    site_name = "rotowire"
    base_url = "https://www.rotowire.com"

    # Entry points for betting content
    PATHS = [
        "/betting/nba/player-props",
        "/betting/nba/best-bets",
        "/betting/ncaab/best-bets",
        "/betting/nfl/best-bets",
    ]

    async def scrape(self) -> list[dict]:
        articles: list[dict] = []
        for path in self.PATHS:
            url = f"{self.base_url}{path}"
            try:
                resp = await self.fetch(url)
            except Exception as e:
                print(f"[rotowire] Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            articles.extend(self._parse_page(soup, url, path))

        return articles

    def _parse_page(self, soup: BeautifulSoup, url: str, path: str) -> list[dict]:
        """Extract articles / pick cards from a RotoWire betting page."""
        results: list[dict] = []
        sport = self._sport_from_path(path)
        category = "player_props" if "player-props" in path else "best_bets"

        # RotoWire uses article cards with class 'betting-pick' or similar
        cards = soup.select("div.betting-pick, article.pick-card, div.article-card")
        if not cards:
            # Fallback: grab the main content area
            main = soup.select_one("main, div.main-content, div#content")
            if main:
                results.append({
                    "title": soup.title.string.strip() if soup.title and soup.title.string else "",
                    "url": url,
                    "content": main.get_text(separator="\n", strip=True),
                    "category": category,
                    "sport": sport,
                    "odds_data": {},
                    "raw_html": str(main),
                })
            return results

        for card in cards:
            title_el = card.select_one("h2, h3, .pick-title, .article-title")
            title = title_el.get_text(strip=True) if title_el else ""
            content = card.get_text(separator="\n", strip=True)

            # Try to extract odds from the card
            odds_data = {}
            odds_el = card.select_one(".odds, .line, .spread")
            if odds_el:
                odds_data["display"] = odds_el.get_text(strip=True)

            link_el = card.select_one("a[href]")
            article_url = url
            if link_el and link_el.get("href", "").startswith("/"):
                article_url = f"{self.base_url}{link_el['href']}"
            elif link_el and link_el.get("href", "").startswith("http"):
                article_url = link_el["href"]

            results.append({
                "title": title,
                "url": article_url,
                "content": content,
                "category": category,
                "sport": sport,
                "odds_data": odds_data,
                "raw_html": str(card),
            })

        return results

    @staticmethod
    def _sport_from_path(path: str) -> str:
        path_lower = path.lower()
        for sport in ("nba", "ncaab", "nfl", "mlb", "nhl"):
            if sport in path_lower:
                return sport.upper()
        return "UNKNOWN"


if __name__ == "__main__":
    asyncio.run(RotoWireScraper().run())
