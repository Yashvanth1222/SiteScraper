#!/usr/bin/env python3
"""SiteScraper — main CLI orchestrator.

Usage:
    python main.py                  Run full pipeline once
    python main.py --schedule       Start daily scheduler (6 AM ET)
    python main.py --scrape-only    Only run scrapers
    python main.py --rewrite-only   Only run rewriter on existing raw data
    python main.py --publish-only   Only publish existing processed articles
    python main.py --site rotowire  Run pipeline for a specific site
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

from config import Config
from publisher.blog import FilePublisher, WebflowPublisher
from publisher.formatter import Formatter
from publisher.scheduler import PipelineScheduler

logger = logging.getLogger("sitescraper")

# Map site names → scraper classes
_SCRAPER_MAP: dict[str, str] = {
    "rotowire": "RotoWireScraper",
    "bettingpros": "BettingProsScraper",
    "oddsshark": "OddsSharkScraper",
    "covers": "CoversScraper",
}


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

async def run_scrapers(cfg: Config, sites: tuple[str, ...] | None = None) -> None:
    """Scrape all (or selected) target sites in parallel."""
    targets = sites or cfg.sites
    logger.info("Scraping sites: %s", ", ".join(targets))

    async def _scrape_one(site: str) -> None:
        class_name = _SCRAPER_MAP.get(site)
        if not class_name:
            logger.error("Unknown site: %s — skipping", site)
            return
        try:
            mod = __import__(f"scrapers.{site}", fromlist=[class_name])
            scraper_cls = getattr(mod, class_name)
            scraper = scraper_cls()
            await scraper.run()
            logger.info("Scraper finished: %s", site)
        except ModuleNotFoundError:
            logger.error("Scraper module not found: scrapers.%s — skipping", site)
        except Exception:
            logger.exception("Scraper failed: %s — continuing with others", site)

    await asyncio.gather(*[_scrape_one(s) for s in targets])


async def run_rewriter(cfg: Config, date_str: str | None = None) -> None:
    """Run AI rewriter on today's raw data from all sites."""
    import json as _json
    logger.info("Running rewriter on raw data")
    try:
        from rewriter import RewriterEngine
    except ImportError:
        logger.error("Rewriter module not found — skipping")
        return

    target_date = date_str or str(date.today())
    engine = RewriterEngine(api_key=cfg.anthropic_api_key or None)

    raw_dir = cfg.raw_dir
    if not raw_dir.exists():
        logger.warning("No raw data directory found")
        return

    for site_dir in sorted(raw_dir.iterdir()):
        if not site_dir.is_dir():
            continue
        json_file = site_dir / f"{target_date}.json"
        if not json_file.exists():
            logger.info("No raw data for %s on %s", site_dir.name, target_date)
            continue

        try:
            source_data = _json.loads(json_file.read_text())
            for article in source_data.get("articles", []):
                content_type = article.get("category", "best_bets")
                sport = article.get("sport", "NBA")
                await engine.rewrite_and_save(
                    source_data=article,
                    content_type=content_type,
                    sport=sport,
                    article_date=target_date,
                )
            logger.info("Rewriter finished for %s", site_dir.name)
        except Exception:
            logger.exception("Rewriter failed for %s", site_dir.name)


async def run_publisher(
    cfg: Config,
    date_str: str | None = None,
    use_webflow: bool = False,
) -> None:
    """Format and publish processed articles."""
    formatter = Formatter(cfg.processed_dir)

    if use_webflow:
        if not cfg.webflow_api_token or not cfg.webflow_collection_id:
            logger.error(
                "WEBFLOW_API_TOKEN and WEBFLOW_COLLECTION_ID must be set "
                "to use --webflow mode"
            )
            return
        publisher = WebflowPublisher(
            api_token=cfg.webflow_api_token,
            collection_id=cfg.webflow_collection_id,
            published_dir=cfg.published_dir,
        )
    else:
        publisher = FilePublisher(cfg.published_dir)

    articles = await formatter.format_all(date_str)
    if not articles:
        logger.warning("No articles to publish")
        return

    for article in articles:
        await publisher.publish(article)

    logger.info("Published %d article(s)", len(articles))

    if use_webflow and hasattr(publisher, "close"):
        await publisher.close()


async def run_full_pipeline(
    cfg: Config,
    sites: tuple[str, ...] | None = None,
    date_str: str | None = None,
    use_webflow: bool = False,
) -> None:
    """Execute the complete scrape → rewrite → publish pipeline."""
    logger.info("=== Starting full pipeline ===")
    await run_scrapers(cfg, sites)
    await run_rewriter(cfg, date_str)
    await run_publisher(cfg, date_str, use_webflow=use_webflow)
    logger.info("=== Pipeline complete ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _setup_logging(cfg: Config) -> None:
    log_dir = cfg.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "pipeline.log"),
    ]
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitescraper",
        description="Automated sports-betting content pipeline",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--schedule", action="store_true",
        help="Start the APScheduler for daily automated runs",
    )
    mode.add_argument(
        "--scrape-only", action="store_true",
        help="Only run scrapers (no rewrite/publish)",
    )
    mode.add_argument(
        "--rewrite-only", action="store_true",
        help="Only rewrite existing raw data (no scrape/publish)",
    )
    mode.add_argument(
        "--publish-only", action="store_true",
        help="Only publish already-processed articles",
    )
    parser.add_argument(
        "--site", type=str, default=None,
        help="Run pipeline for a single site (e.g. rotowire)",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Target date in YYYY-MM-DD format (defaults to today)",
    )
    parser.add_argument(
        "--webflow", action="store_true",
        help="Publish to Webflow CMS instead of local files",
    )
    return parser


def main() -> None:
    cfg = Config.from_env()
    _setup_logging(cfg)

    parser = build_parser()
    args = parser.parse_args()

    sites = (args.site,) if args.site else None
    target_date = args.date or str(date.today())

    use_webflow = args.webflow

    if args.schedule:
        logger.info("Starting scheduler mode")
        scheduler = PipelineScheduler(
            run_pipeline_fn=lambda: run_full_pipeline(
                cfg, sites, use_webflow=use_webflow
            ),
            hour=cfg.schedule_hour,
            minute=cfg.schedule_minute,
            log_dir=cfg.log_dir,
        )
        scheduler.run_blocking()
    elif args.scrape_only:
        asyncio.run(run_scrapers(cfg, sites))
    elif args.rewrite_only:
        asyncio.run(run_rewriter(cfg, target_date))
    elif args.publish_only:
        asyncio.run(run_publisher(cfg, target_date, use_webflow=use_webflow))
    else:
        asyncio.run(run_full_pipeline(cfg, sites, target_date, use_webflow=use_webflow))


if __name__ == "__main__":
    main()
