"""Tests for the publisher package — formatter, manifest tracking, Webflow."""

from __future__ import annotations

import asyncio
import json
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from publisher.blog import FilePublisher, Manifest, WebflowPublisher, _slugify
from publisher.formatter import (
    Formatter,
    _parse_frontmatter,
    build_rss_item,
    md_to_html,
    wrap_blog_html,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_MD = textwrap.dedent("""\
    ---
    title: Best NBA Bets Today
    slug: best-nba-bets-today
    category: NBA
    tags:
      - NBA
      - player props
    date: "2026-02-17"
    ---
    ## Top Picks

    Here are today's **best bets** for the NBA.

    1. Lakers ML
    2. Celtics -5.5
""")


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        meta, body = _parse_frontmatter(SAMPLE_MD)
        assert meta["title"] == "Best NBA Bets Today"
        assert meta["slug"] == "best-nba-bets-today"
        assert "Top Picks" in body

    def test_no_frontmatter(self):
        meta, body = _parse_frontmatter("Just plain markdown.\n")
        assert meta == {}
        assert "Just plain markdown." in body


# ---------------------------------------------------------------------------
# Markdown → HTML
# ---------------------------------------------------------------------------

class TestMdToHtml:
    def test_basic_conversion(self):
        html = md_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_heading(self):
        html = md_to_html("## Heading Two")
        assert "<h2" in html


# ---------------------------------------------------------------------------
# Blog HTML wrapper
# ---------------------------------------------------------------------------

class TestWrapBlogHtml:
    def test_contains_title_and_author(self):
        html = wrap_blog_html("My Title", "<p>Body</p>", {"date": "2026-02-17"})
        assert "<h1>My Title</h1>" in html
        assert "Novig AI" in html
        assert "2026-02-17" in html

    def test_tags_rendered(self):
        html = wrap_blog_html("T", "<p>B</p>", {"tags": ["NBA", "Props"]})
        assert "NBA" in html
        assert "Props" in html


# ---------------------------------------------------------------------------
# RSS snippet
# ---------------------------------------------------------------------------

class TestBuildRssItem:
    def test_basic_rss(self):
        xml = build_rss_item("Title", "my-slug", "A description", "2026-02-17")
        assert "<title>Title</title>" in xml
        assert "my-slug" in xml
        assert "<pubDate>2026-02-17</pubDate>" in xml

    def test_xml_escaping(self):
        xml = build_rss_item("A & B <C>", "slug", "desc", "2026-02-17")
        assert "&amp;" in xml
        assert "&lt;C&gt;" in xml


# ---------------------------------------------------------------------------
# Manifest tracking
# ---------------------------------------------------------------------------

class TestManifest:
    @pytest.fixture()
    def manifest_path(self, tmp_path: Path) -> Path:
        return tmp_path / "manifest.json"

    def test_empty_manifest(self, manifest_path: Path):
        m = Manifest(manifest_path)
        data = asyncio.run(m.load())
        assert data == {"articles": []}

    def test_add_and_contains(self, manifest_path: Path):
        m = Manifest(manifest_path)
        asyncio.run(m.add({"slug": "test-article", "title": "Test"}))
        assert asyncio.run(m.contains("test-article"))
        assert not asyncio.run(m.contains("nonexistent"))

    def test_persistence(self, manifest_path: Path):
        m = Manifest(manifest_path)
        asyncio.run(m.add({"slug": "a1", "title": "A1"}))
        # Create a fresh Manifest instance to verify file persistence
        m2 = Manifest(manifest_path)
        assert asyncio.run(m2.contains("a1"))


# ---------------------------------------------------------------------------
# FilePublisher
# ---------------------------------------------------------------------------

class TestFilePublisher:
    @pytest.fixture()
    def publisher(self, tmp_path: Path) -> FilePublisher:
        return FilePublisher(tmp_path / "published")

    def test_publish_creates_files(self, publisher: FilePublisher):
        article = {
            "slug": "test-article",
            "title": "Test Article",
            "html": "<p>Hello</p>",
            "rss_xml": "<item/>",
            "date": "2026-02-17",
        }
        slug = asyncio.run(publisher.publish(article))
        assert slug == "test-article"

        html_path = publisher.published_dir / "2026-02-17" / "test-article.html"
        assert html_path.exists()
        assert "<p>Hello</p>" in html_path.read_text()

        rss_path = publisher.published_dir / "2026-02-17" / "test-article.rss.xml"
        assert rss_path.exists()

    def test_duplicate_skipped(self, publisher: FilePublisher):
        article = {
            "slug": "dup",
            "title": "Dup",
            "html": "<p>1</p>",
            "rss_xml": "",
            "date": "2026-02-17",
        }
        asyncio.run(publisher.publish(article))
        # Publish again — should be a no-op
        asyncio.run(publisher.publish(article))

        manifest_path = publisher.published_dir / "manifest.json"
        data = json.loads(manifest_path.read_text())
        slugs = [a["slug"] for a in data["articles"]]
        assert slugs.count("dup") == 1


# ---------------------------------------------------------------------------
# Formatter (integration-ish)
# ---------------------------------------------------------------------------

class TestFormatter:
    @pytest.fixture()
    def processed_dir(self, tmp_path: Path) -> Path:
        day_dir = tmp_path / "2026-02-17"
        day_dir.mkdir()
        (day_dir / "best-nba-bets-today.md").write_text(SAMPLE_MD)
        return tmp_path

    def test_format_article(self, processed_dir: Path):
        formatter = Formatter(processed_dir)
        md_path = processed_dir / "2026-02-17" / "best-nba-bets-today.md"
        result = asyncio.run(formatter.format_article(md_path))

        assert result["slug"] == "best-nba-bets-today"
        assert result["title"] == "Best NBA Bets Today"
        assert "<article" in result["html"]
        assert "<item>" in result["rss_xml"]

    def test_format_all(self, processed_dir: Path):
        formatter = Formatter(processed_dir)
        results = asyncio.run(formatter.format_all("2026-02-17"))
        assert len(results) == 1
        assert results[0]["slug"] == "best-nba-bets-today"

    def test_format_all_missing_date(self, processed_dir: Path):
        formatter = Formatter(processed_dir)
        results = asyncio.run(formatter.format_all("1999-01-01"))
        assert results == []


# ---------------------------------------------------------------------------
# _slugify helper
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert _slugify("Best NBA Bets Today") == "best-nba-bets-today"

    def test_special_characters(self):
        assert _slugify("A & B: The (Remix)!") == "a-b-the-remix"

    def test_truncation(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 60


# ---------------------------------------------------------------------------
# WebflowPublisher
# ---------------------------------------------------------------------------

class TestWebflowPublisher:
    @pytest.fixture()
    def publisher(self, tmp_path: Path) -> WebflowPublisher:
        return WebflowPublisher(
            api_token="test-token",
            collection_id="test-collection-id",
            published_dir=tmp_path / "published",
        )

    def _make_article(self, slug: str = "test-article") -> dict:
        return {
            "slug": slug,
            "title": "Test Article",
            "html": "<p>Hello</p>",
            "rss_xml": "<item/>",
            "date": "2026-02-17",
            "meta": {
                "meta_description": "A test article",
                "category": "NBA",
            },
        }

    def test_build_field_data(self, publisher: WebflowPublisher):
        article = self._make_article()
        fields = publisher._build_field_data(article)
        assert fields["name"] == "Test Article"
        assert fields["slug"] == "test-article"
        assert fields["post-body"] == "<p>Hello</p>"
        assert fields["post-summary"] == "A test article"
        assert fields["category"] == "NBA"
        assert fields["author"] == "Novig AI"
        assert fields["date"] == "2026-02-17"

    def test_publish_success(self, publisher: WebflowPublisher):
        article = self._make_article()
        mock_response = httpx.Response(
            status_code=202,
            json={"id": "wf-item-123"},
            request=httpx.Request("POST", "https://api.webflow.com/v2/collections/x/items"),
        )
        with patch.object(publisher, "_post_with_retry", new_callable=AsyncMock, return_value=mock_response):
            slug = asyncio.run(publisher.publish(article))
        assert slug == "test-article"
        assert asyncio.run(publisher.manifest.contains("test-article"))

    def test_publish_duplicate_skipped(self, publisher: WebflowPublisher):
        article = self._make_article()
        # Pre-populate manifest
        asyncio.run(publisher.manifest.add({"slug": "test-article", "title": "Test"}))
        # Should not call the API at all
        with patch.object(publisher, "_post_with_retry", new_callable=AsyncMock) as mock_post:
            slug = asyncio.run(publisher.publish(article))
        assert slug == "test-article"
        mock_post.assert_not_called()

    def test_publish_auth_failure_raises(self, publisher: WebflowPublisher):
        article = self._make_article()
        mock_response = httpx.Response(
            status_code=401,
            text="Unauthorized",
            request=httpx.Request("POST", "https://api.webflow.com/v2/collections/x/items"),
        )
        with patch.object(publisher, "_post_with_retry", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RuntimeError, match="401"):
                asyncio.run(publisher.publish(article))

    def test_publish_rate_limit_raises(self, publisher: WebflowPublisher):
        article = self._make_article()
        mock_response = httpx.Response(
            status_code=429,
            text="Rate limited",
            request=httpx.Request("POST", "https://api.webflow.com/v2/collections/x/items"),
        )
        with patch.object(publisher, "_post_with_retry", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RuntimeError, match="429"):
                asyncio.run(publisher.publish(article))

    def test_headers(self, publisher: WebflowPublisher):
        headers = publisher._headers()
        assert headers["Authorization"] == "Bearer test-token"
        assert headers["Content-Type"] == "application/json"

    def test_live_mode_sets_is_draft_false(self, publisher: WebflowPublisher):
        publisher_live = WebflowPublisher(
            api_token="t",
            collection_id="c",
            published_dir=publisher.manifest.path.parent,
            live=True,
        )
        article = self._make_article("live-test")
        mock_response = httpx.Response(
            status_code=202,
            json={"id": "wf-live-1"},
            request=httpx.Request("POST", "https://api.webflow.com/v2/collections/c/items"),
        )
        captured_payload = {}

        async def fake_post(url, payload):
            captured_payload.update(payload)
            return mock_response

        with patch.object(publisher_live, "_post_with_retry", side_effect=fake_post):
            asyncio.run(publisher_live.publish(article))

        assert captured_payload["isDraft"] is False
