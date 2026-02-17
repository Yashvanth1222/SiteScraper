"""AI rewriting engine powered by Claude."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from rewriter.seo import SEOResult, SEOValidator
from rewriter.templates import get_template

logger = logging.getLogger(__name__)

# Default keywords that should appear in every article
DEFAULT_KEYWORDS = ["Novig", "prediction markets"]

# Output directory
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"


def _build_frontmatter(
    title: str,
    meta_description: str,
    content_type: str,
    sport: str,
    source: str,
    article_date: str,
    keywords: list[str],
    seo_score: int,
) -> str:
    """Return YAML frontmatter block."""
    kw_yaml = json.dumps(keywords)
    return (
        "---\n"
        f'title: "{title}"\n'
        f'meta_description: "{meta_description}"\n'
        f'category: "{content_type}"\n'
        f'sport: "{sport}"\n'
        f'source: "{source}"\n'
        f'date: "{article_date}"\n'
        f"keywords: {kw_yaml}\n"
        f"seo_score: {seo_score}\n"
        "---\n"
    )


def parse_claude_response(text: str) -> tuple[str, str, str]:
    """Extract title, meta description, and body from Claude's response.

    Expected format in the response::

        TITLE: <headline>
        META_DESCRIPTION: <meta description>
        BODY:
        <markdown body>

    Returns (title, meta_description, body).
    """
    title = ""
    meta_description = ""
    body = ""

    title_match = re.search(r"^TITLE:\s*(.+)$", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip().strip('"')

    meta_match = re.search(r"^META_DESCRIPTION:\s*(.+)$", text, re.MULTILINE)
    if meta_match:
        meta_description = meta_match.group(1).strip().strip('"')

    body_match = re.search(r"^BODY:\s*\n(.*)", text, re.MULTILINE | re.DOTALL)
    if body_match:
        body = body_match.group(1).strip()

    return title, meta_description, body


class RewriterEngine:
    """Rewrites scraped content into SEO-optimized Novig blog articles.

    Parameters
    ----------
    api_key:
        Anthropic API key.  If ``None``, the ``ANTHROPIC_API_KEY`` env var
        is used (handled by the SDK).
    model:
        Claude model to use.
    max_tokens:
        Maximum tokens for the Claude response.
    """

    MODEL = "claude-sonnet-4-6"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model or self.MODEL
        self.max_tokens = max_tokens
        self.seo_validator = SEOValidator()

    async def rewrite(
        self,
        source_data: dict[str, Any],
        content_type: str,
        sport: str = "NBA",
        article_date: str | None = None,
        keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        """Rewrite scraped data into a finished Markdown article.

        Parameters
        ----------
        source_data:
            Raw scraped data dict (as loaded from ``data/raw/``).
        content_type:
            One of: best_bets, player_props, odds_analysis, predictions.
        sport:
            Sport name for the article.
        article_date:
            ISO date string.  Defaults to today.
        keywords:
            Target SEO keywords.  Defaults include "Novig" and
            "prediction markets".

        Returns
        -------
        dict with keys: title, meta_description, body, markdown,
        seo_result, content_type, sport, source, date, keywords.
        """
        article_date = article_date or date.today().isoformat()
        keywords = list(set((keywords or []) + DEFAULT_KEYWORDS))
        source = source_data.get("source", "unknown")

        template = get_template(content_type)
        prompt = template.format(
            sport=sport,
            date=article_date,
            source_data=json.dumps(source_data, indent=2),
            keywords=", ".join(keywords),
        )

        logger.info(
            "Rewriting %s article for %s from %s", content_type, sport, source
        )

        message = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text
        title, meta_description, body = parse_claude_response(response_text)

        seo_result = self.seo_validator.validate(
            title=title,
            meta_description=meta_description,
            body=body,
            keywords=keywords,
        )

        frontmatter = _build_frontmatter(
            title=title,
            meta_description=meta_description,
            content_type=content_type,
            sport=sport,
            source=source,
            article_date=article_date,
            keywords=keywords,
            seo_score=seo_result.score,
        )

        markdown = frontmatter + "\n" + body

        return {
            "title": title,
            "meta_description": meta_description,
            "body": body,
            "markdown": markdown,
            "seo_result": seo_result,
            "content_type": content_type,
            "sport": sport,
            "source": source,
            "date": article_date,
            "keywords": keywords,
        }

    async def rewrite_and_save(
        self,
        source_data: dict[str, Any],
        content_type: str,
        sport: str = "NBA",
        article_date: str | None = None,
        keywords: list[str] | None = None,
        output_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Rewrite and persist the article to ``data/processed/{date}/``.

        Returns the same dict as :meth:`rewrite`, with an added
        ``output_path`` key.
        """
        result = await self.rewrite(
            source_data=source_data,
            content_type=content_type,
            sport=sport,
            article_date=article_date,
            keywords=keywords,
        )

        out_dir = output_dir or PROCESSED_DIR / result["date"]
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build a safe filename from the title
        safe_title = re.sub(r"[^\w\s-]", "", result["title"]).strip()
        safe_title = re.sub(r"[\s]+", "-", safe_title).lower()[:60]
        filename = f"{result['content_type']}_{safe_title}.md"

        out_path = out_dir / filename
        out_path.write_text(result["markdown"], encoding="utf-8")

        logger.info("Saved article to %s", out_path)
        result["output_path"] = out_path
        return result
