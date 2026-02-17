"""BettingPros scraper — prop bet recommendations, odds comparisons."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class BettingProsScraper(BaseScraper):
    site_name = "bettingpros"
    base_url = "https://www.bettingpros.com"

    PATHS = [
        "/nba/picks/player-props",
        "/nba/odds",
        "/ncaab/picks/player-props",
        "/nfl/picks/player-props",
    ]

    async def scrape(self) -> list[dict]:
        articles: list[dict] = []
        for path in self.PATHS:
            url = f"{self.base_url}{path}"
            try:
                # BettingPros heavily relies on JS rendering
                html = await self.fetch_with_playwright(url)
            except Exception as e:
                print(f"[bettingpros] Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(html, "lxml")
            articles.extend(self._parse_page(soup, url, path))

        return articles

    def _parse_page(self, soup: BeautifulSoup, url: str, path: str) -> list[dict]:
        results: list[dict] = []
        sport = self._sport_from_path(path)
        category = "player_props" if "player-props" in path else "odds_analysis"

        # BettingPros renders prop picks in table rows or card components
        rows = soup.select(
            "tr.picks-table__row, div.prop-card, div.pick-card, div.article-card"
        )

        if not rows:
            main = soup.select_one("main, div.main-content, div#app")
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

        for row in rows:
            player_el = row.select_one(".player-name, td:first-child")
            title = player_el.get_text(strip=True) if player_el else ""
            content = row.get_text(separator="\n", strip=True)

            odds_data = {}
            odds_el = row.select_one(".odds-value, .line-value, .prop-value")
            if odds_el:
                odds_data["display"] = odds_el.get_text(strip=True)

            over_el = row.select_one(".over, .pick-over")
            under_el = row.select_one(".under, .pick-under")
            if over_el:
                odds_data["over"] = over_el.get_text(strip=True)
            if under_el:
                odds_data["under"] = under_el.get_text(strip=True)

            results.append({
                "title": title,
                "url": url,
                "content": content,
                "category": category,
                "sport": sport,
                "odds_data": odds_data,
                "raw_html": str(row),
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
    asyncio.run(BettingProsScraper().run())
