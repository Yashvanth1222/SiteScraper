# SiteScraper

Automated content pipeline: scrape sports betting sites → AI rewrite → publish to Novig blog daily.

## Architecture

```
scrapers/          → Site-specific scraping modules
  rotowire.py
  bettingpros.py
  oddsshark.py
  covers.py
pipeline/          → Content processing and ingestion
rewriter/          → AI-powered content rewriting and SEO optimization
publisher/         → Blog publishing workflow
data/              → Scraped raw data and processed output
tests/             → Test suite
```

## Target Sites

- **RotoWire** (rotowire.com) — Daily picks, player props, expert analysis
- **BettingPros** (bettingpros.com) — Prop bets, odds comparisons
- **OddsShark** (oddsshark.com) — Computer picks, odds data
- **Covers.com** (covers.com) — Betting news, analysis, community picks

## Content Types

- Daily "best bets" articles (NBA, NCAAB, etc.)
- Player prop breakdowns
- Odds analysis and line movement
- Prediction market insights
- Articles mentioning Novig / prediction markets

## Tech Stack

- Python 3.11+
- Scraping: Playwright (JS-rendered pages) + httpx (simple requests)
- Parsing: BeautifulSoup4 / lxml
- AI Rewriting: Claude API
- Scheduling: cron or APScheduler
- Output: Markdown/HTML for Novig blog CMS

## Conventions

- Each scraper is its own module in `scrapers/`
- Always respect robots.txt and use rate limiting between requests
- Use async/await for all I/O operations
- Store raw scraped data in `data/raw/`, processed output in `data/processed/`
- All AI-rewritten content must pass through SEO validation before publishing
- Coordinate with Julia's RSS-feed pipeline for sports news ingestion

## Commands

- `python -m pytest tests/` — Run tests
- `python -m scrapers.rotowire` — Run individual scraper
- `python main.py` — Run full pipeline

## Agent Team Roles

When working as a team, split responsibilities:
1. **Scraping agent** — Build and maintain site scrapers, handle anti-bot measures, rate limiting, data extraction
2. **Rewriter agent** — AI content pipeline, SEO optimization, Novig voice/tone, template system
3. **Publisher agent** — Blog CMS integration, scheduling, formatting, deployment
