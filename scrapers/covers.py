"""Covers.com scraper — betting news, analysis, community picks."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class CoversScraper(BaseScraper):
    site_name = "covers"
    base_url = "https://www.covers.com"

    PATHS = [
        "/nba/betting-news",
        "/nba/odds",
        "/ncaab/betting-news",
        "/nfl/betting-news",
    ]

    async def scrape(self) -> list[dict]:
        articles: list[dict] = []
        for path in self.PATHS:
            url = f"{self.base_url}{path}"
            try:
                resp = await self.fetch(url)
            except Exception as e:
                print(f"[covers] Failed to fetch {url}: {e}")
                continue

            soup = BeautifulSoup(resp.text, "lxml")
            articles.extend(self._parse_page(soup, url, path))

        # Also try to pull individual article links for deeper scraping
        await self._scrape_linked_articles(articles)
        return articles

    def _parse_page(self, soup: BeautifulSoup, url: str, path: str) -> list[dict]:
        results: list[dict] = []
        sport = self._sport_from_path(path)
        is_odds = "odds" in path
        category = "odds_analysis" if is_odds else "best_bets"

        # Covers uses article listing cards
        cards = soup.select(
            "article.article-card, div.article-card, div.news-card, li.article-item"
        )

        if not cards:
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
            title_el = card.select_one("h2, h3, .article-title, .headline")
            title = title_el.get_text(strip=True) if title_el else ""
            content = card.get_text(separator="\n", strip=True)

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
                "odds_data": {},
                "raw_html": str(card),
                "_needs_full_scrape": bool(link_el),
            })

        return results

    async def _scrape_linked_articles(self, articles: list[dict]):
        """Follow article links to get full content (up to 5)."""
        to_scrape = [a for a in articles if a.pop("_needs_full_scrape", False)]
        for article in to_scrape[:5]:
            try:
                resp = await self.fetch(article["url"])
                soup = BeautifulSoup(resp.text, "lxml")
                body = soup.select_one(
                    "article, div.article-body, div.article-content"
                )
                if body:
                    article["content"] = body.get_text(separator="\n", strip=True)
                    article["raw_html"] = str(body)
            except Exception as e:
                print(f"[covers] Failed to fetch article {article['url']}: {e}")

    @staticmethod
    def _sport_from_path(path: str) -> str:
        path_lower = path.lower()
        for sport in ("nba", "ncaab", "nfl", "mlb", "nhl"):
            if sport in path_lower:
                return sport.upper()
        return "UNKNOWN"


if __name__ == "__main__":
    asyncio.run(CoversScraper().run())
