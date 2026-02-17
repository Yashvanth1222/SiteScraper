# SiteScraper

Automated content pipeline that scrapes high-traffic sports betting sites, repurposes the content into SEO-optimized blog posts, and publishes them to the Novig blog daily.

## Goal

Boost Novig's domain authority and organic traffic by publishing a steady stream of fresh, SEO-friendly articles covering betting picks, player props, odds analysis, and prediction markets.

## How It Works

1. **Scrape** — Crawl target sites daily, extract headlines, key points, odds data, and relevant stats
2. **Ingest** — Process and structure the raw content (coordinate with Julia's RSS-feed work for sports news streams)
3. **Rewrite** — Feed extracted data into AI-powered templates to generate original, SEO-optimized articles in Novig's voice
4. **Publish** — Auto-post to the Novig blog on a daily schedule

## Target Sites

| Site | Content Type |
|------|-------------|
| [RotoWire](https://www.rotowire.com) | Daily picks, player props, expert analysis articles |
| [BettingPros](https://www.bettingpros.com) | Prop bet recommendations, odds comparisons across sportsbooks |
| [OddsShark](https://www.oddsshark.com) | Computer-generated picks, odds data |
| [Covers.com](https://www.covers.com) | Betting news, analysis, community picks |

## Content Types to Generate

- Daily "best bets" articles (NBA, NCAAB, etc.)
- Player prop breakdowns
- Odds analysis and line movement
- Prediction market insights
- Articles that mention Novig / prediction markets

## Integration

- Coordinate with Julia's RSS-feed pipeline for sports news ingestion
- Shared content formatting for Novig blog CMS

## Next Steps

- [ ] Research scraping solution that can handle all target sites (JS-rendered pages, rate limiting, etc.)
- [ ] Design the content extraction pipeline (what data to pull from each site)
- [ ] Build AI rewriting/templating system for SEO-optimized output
- [ ] Set up daily scheduling (cron / task runner)
- [ ] Create publishing workflow to format and post to Novig blog
- [ ] Coordinate with Julia on RSS-feed integration
