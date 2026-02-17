"""Content ingestion pipeline.

Reads raw scraped JSON from ``data/raw/``, deduplicates, feeds articles
through the rewriter, runs SEO validation, and saves output to
``data/processed/``.
"""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from rewriter.engine import RewriterEngine

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# Similarity threshold for deduplication (0-1).  Articles with title
# similarity above this value are considered duplicates.
DEDUP_THRESHOLD = 0.85


def _title_similarity(a: str, b: str) -> float:
    """Return a 0-1 similarity score between two titles."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _is_duplicate(
    article: dict[str, Any], seen: list[dict[str, Any]]
) -> bool:
    """Check if *article* is a duplicate of anything in *seen*.

    Deduplicates by exact URL match or high title similarity.
    """
    url = article.get("url", "")
    title = article.get("title", "")

    for prev in seen:
        if url and url == prev.get("url", ""):
            return True
        prev_title = prev.get("title", "")
        if title and prev_title and _title_similarity(title, prev_title) >= DEDUP_THRESHOLD:
            return True
    return False


class PipelineProcessor:
    """Orchestrates the scrape -> rewrite -> validate -> save pipeline.

    Parameters
    ----------
    engine:
        A configured :class:`RewriterEngine` instance.
    raw_dir:
        Path to the raw scraped JSON directory.  Defaults to ``data/raw/``.
    processed_dir:
        Path to the processed output directory.  Defaults to ``data/processed/``.
    """

    def __init__(
        self,
        engine: RewriterEngine,
        raw_dir: Path | None = None,
        processed_dir: Path | None = None,
    ) -> None:
        self.engine = engine
        self.raw_dir = raw_dir or RAW_DIR
        self.processed_dir = processed_dir or PROCESSED_DIR

    def load_raw_articles(self) -> list[dict[str, Any]]:
        """Load all JSON files from the raw data directory.

        Each JSON file should contain either a single article dict or a
        list of article dicts with at minimum: ``title``, ``content``,
        ``source``, ``url``, ``content_type``, ``sport``.
        """
        articles: list[dict[str, Any]] = []
        if not self.raw_dir.exists():
            logger.warning("Raw data directory does not exist: %s", self.raw_dir)
            return articles

        for json_path in sorted(self.raw_dir.glob("**/*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    articles.extend(data)
                elif isinstance(data, dict):
                    articles.append(data)
                else:
                    logger.warning("Unexpected JSON structure in %s", json_path)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("Failed to load %s: %s", json_path, exc)

        logger.info("Loaded %d raw articles from %s", len(articles), self.raw_dir)
        return articles

    def deduplicate(
        self, articles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate articles by URL and title similarity."""
        unique: list[dict[str, Any]] = []
        for article in articles:
            if not _is_duplicate(article, unique):
                unique.append(article)
            else:
                logger.debug(
                    "Skipping duplicate: %s", article.get("title", "untitled")
                )

        removed = len(articles) - len(unique)
        if removed:
            logger.info("Removed %d duplicate articles", removed)
        return unique

    async def process_article(
        self,
        article: dict[str, Any],
        article_date: str | None = None,
    ) -> dict[str, Any] | None:
        """Rewrite a single article and run SEO validation.

        Returns the result dict on success, or ``None`` if the article
        fails SEO validation.
        """
        content_type = article.get("content_type", "best_bets")
        sport = article.get("sport", "NBA")
        keywords = article.get("keywords", [])

        try:
            result = await self.engine.rewrite_and_save(
                source_data=article,
                content_type=content_type,
                sport=sport,
                article_date=article_date,
                keywords=keywords,
                output_dir=self.processed_dir / (article_date or "latest"),
            )
        except Exception:
            logger.exception(
                "Failed to rewrite article: %s", article.get("title", "untitled")
            )
            return None

        seo = result["seo_result"]
        if not seo.passed:
            logger.warning(
                "Article failed SEO validation (score %d): %s\n%s",
                seo.score,
                result["title"],
                seo,
            )
        else:
            logger.info(
                "Article passed SEO (score %d): %s", seo.score, result["title"]
            )

        return result

    async def run(
        self, article_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Run the full pipeline: load -> deduplicate -> rewrite -> save.

        Returns a list of result dicts for all processed articles.
        """
        articles = self.load_raw_articles()
        if not articles:
            logger.info("No raw articles to process")
            return []

        articles = self.deduplicate(articles)

        results: list[dict[str, Any]] = []
        for article in articles:
            result = await self.process_article(
                article, article_date=article_date
            )
            if result is not None:
                results.append(result)

        passed = sum(1 for r in results if r["seo_result"].passed)
        logger.info(
            "Pipeline complete: %d/%d articles passed SEO validation",
            passed,
            len(results),
        )
        return results
