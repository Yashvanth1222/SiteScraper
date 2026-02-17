"""OddsShark scraper — computer-generated picks, odds data."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class OddsSharkScraper(BaseScraper):
    site_name = "oddsshark"
    base_url = "https://www.oddsshark.com"

    PATHS = [
        "/nba/computer-picks",
        "/nba/odds",
        "/ncaab/computer-picks",
        "/nfl/computer-picks",
    ]

    async def scrape(self) -> list[dict]:
        articles: list[dict] = []
        for path in self.PATHS:
            url = f"{self.base_url}{path}"
            try:
                # OddsShark uses JS rendering for odds tables
                html = await self.fetch_with_playwright(url)
            except Exception as e:
                print(f"[oddsshark] Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(html, "lxml")
            articles.extend(self._parse_page(soup, url, path))

        return articles

    def _parse_page(self, soup: BeautifulSoup, url: str, path: str) -> list[dict]:
        results: list[dict] = []
        sport = self._sport_from_path(path)
        is_picks = "computer-picks" in path
        category = "predictions" if is_picks else "odds_analysis"

        # OddsShark renders matchup rows in tables
        rows = soup.select(
            "div.matchup, tr.matchup-row, div.game-card, div.odds-row"
        )

        if not rows:
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

        for row in rows:
            teams_el = row.select_one(".teams, .matchup-teams, .game-teams")
            title = teams_el.get_text(strip=True) if teams_el else ""
            content = row.get_text(separator="\n", strip=True)

            odds_data = {}
            spread_el = row.select_one(".spread, .line")
            total_el = row.select_one(".total, .over-under")
            ml_el = row.select_one(".moneyline, .ml")
            pick_el = row.select_one(".computer-pick, .prediction")

            if spread_el:
                odds_data["spread"] = spread_el.get_text(strip=True)
            if total_el:
                odds_data["total"] = total_el.get_text(strip=True)
            if ml_el:
                odds_data["moneyline"] = ml_el.get_text(strip=True)
            if pick_el:
                odds_data["computer_pick"] = pick_el.get_text(strip=True)

            link_el = row.select_one("a[href]")
            matchup_url = url
            if link_el and link_el.get("href", "").startswith("/"):
                matchup_url = f"{self.base_url}{link_el['href']}"
            elif link_el and link_el.get("href", "").startswith("http"):
                matchup_url = link_el["href"]

            results.append({
                "title": title,
                "url": matchup_url,
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
    asyncio.run(OddsSharkScraper().run())
