"""Convert processed Markdown articles into blog-ready HTML and RSS snippets."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import aiofiles
import markdown
import yaml

logger = logging.getLogger(__name__)

# Markdown extensions for richer HTML output
_MD = markdown.Markdown(extensions=["extra", "smarty", "toc"])


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from Markdown body.

    Expected format:
        ---
        title: ...
        slug: ...
        ---
        Body text here.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)
    return meta, body


def md_to_html(body: str) -> str:
    """Convert a Markdown string to HTML."""
    _MD.reset()
    return _MD.convert(body)


def wrap_blog_html(title: str, html_body: str, meta: dict[str, Any]) -> str:
    """Wrap raw HTML in a blog article template."""
    category = meta.get("category", "Sports Betting")
    tags = meta.get("tags", [])
    tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
    today = meta.get("date", str(date.today()))

    return f"""\
<article class="blog-post">
  <header>
    <h1>{title}</h1>
    <div class="meta">
      <span class="author">Novig AI</span>
      <time datetime="{today}">{today}</time>
      <span class="category">{category}</span>
    </div>
    {f'<div class="tags">{tag_html}</div>' if tag_html else ''}
    <!-- featured image placeholder -->
    <div class="featured-image" data-src=""></div>
  </header>
  <div class="content">
{html_body}
  </div>
</article>
"""


def build_rss_item(title: str, slug: str, description: str, pub_date: str) -> str:
    """Generate an RSS <item> XML snippet for Julia's RSS pipeline."""
    return f"""\
<item>
  <title>{xml_escape(title)}</title>
  <link>https://novig.com/blog/{xml_escape(slug)}</link>
  <description>{xml_escape(description)}</description>
  <pubDate>{xml_escape(pub_date)}</pubDate>
  <author>Novig AI</author>
</item>
"""


class Formatter:
    """Read processed .md files, produce blog HTML + RSS snippets."""

    def __init__(self, processed_dir: Path) -> None:
        self.processed_dir = processed_dir

    async def format_article(self, md_path: Path) -> dict[str, Any]:
        """Return a dict with keys: slug, title, html, rss_xml, date, meta."""
        async with aiofiles.open(md_path, "r") as f:
            raw = await f.read()

        meta, body = _parse_frontmatter(raw)
        title = meta.get("title", md_path.stem.replace("-", " ").title())
        slug = meta.get("slug", md_path.stem)
        today = meta.get("date", str(date.today()))

        html_body = md_to_html(body)
        full_html = wrap_blog_html(title, html_body, {**meta, "date": today})

        # Use the first 200 chars of body as RSS description
        description = body[:200].replace("\n", " ").strip()
        rss_xml = build_rss_item(title, slug, description, today)

        return {
            "slug": slug,
            "title": title,
            "html": full_html,
            "rss_xml": rss_xml,
            "date": today,
            "meta": meta,
        }

    async def format_all(self, date_str: str | None = None) -> list[dict[str, Any]]:
        """Format all .md files for a given date (defaults to today)."""
        target_date = date_str or str(date.today())
        day_dir = self.processed_dir / target_date

        if not day_dir.exists():
            logger.warning("No processed articles found for %s", target_date)
            return []

        results = []
        for md_file in sorted(day_dir.glob("*.md")):
            try:
                article = await self.format_article(md_file)
                results.append(article)
                logger.info("Formatted %s", md_file.name)
            except Exception:
                logger.exception("Failed to format %s", md_file)
        return results
