"""Tests for the rewriter pipeline.

SEO validation is tested directly.  Claude API calls are mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rewriter.engine import RewriterEngine, parse_claude_response
from rewriter.seo import SEOValidator
from rewriter.templates import CONTENT_TYPES, get_template
from pipeline.processor import PipelineProcessor, _title_similarity, _is_duplicate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ARTICLE = {
    "title": "NBA Best Bets for February 17",
    "content": "The Lakers are favored by 5.5 against the Celtics tonight...",
    "source": "rotowire",
    "url": "https://rotowire.com/nba/best-bets-2026-02-17",
    "content_type": "best_bets",
    "sport": "NBA",
    "keywords": ["NBA picks", "Lakers vs Celtics"],
}

# A realistic Claude response that should pass SEO validation
MOCK_CLAUDE_RESPONSE = """\
TITLE: NBA Best Bets Today: Top Prediction Market Picks
META_DESCRIPTION: Discover today's top NBA prediction market opportunities. Our data-driven analysis reveals the best forecasts for tonight's games on Novig.
BODY:
# NBA Best Bets Today: Top Prediction Market Picks

The NBA season is in full swing, and today's slate offers several compelling
prediction market opportunities. At {{novig_internal_link}}, we analyze the
numbers to find where the market may be mispricing outcomes.

## Lakers vs Celtics: A Clash of Titans

The Lakers are favored by 5.5 points tonight, but our models suggest this
line may be too generous. Historical data shows that when these teams meet in
February, the underdog covers 58% of the time. This is a classic example of
where prediction markets can offer an edge over traditional analysis.

The Celtics have been on a strong run, winning 7 of their last 10 games.
Their defensive rating has improved significantly, ranking 3rd in the league
over the past month. Meanwhile, the Lakers have struggled on the road,
going just 4-6 in their last 10 away games.

## Bucks vs Nuggets: Value in the Total

Tonight's Bucks-Nuggets matchup has a total set at 228.5, but our analysis
points to the over as a strong forecast. Both teams rank in the top 10 in
pace this season, and their previous meetings have averaged 235 points.

Giannis Antetokounmpo has been averaging 32.5 points over his last five
games, while Nikola Jokic continues his MVP-caliber season with a 27-12-10
stat line. When both stars are firing, this total looks low.

## Knicks vs Heat: The Spread Tell

The Knicks opened as 2-point favorites but the line has moved to -3.5,
suggesting sharp money is backing New York. On Novig's prediction markets,
this kind of line movement often signals informed forecasting activity.

The Knicks' home court advantage this season has been remarkable, with a
15-3 record at Madison Square Garden. Their defensive efficiency at home
ranks 2nd in the league, making them a strong pick tonight.

## How to Use These Forecasts

These picks are best used as starting points for your own prediction market
analysis. At Novig, we believe in data-driven forecasting that combines
statistical models with market intelligence.

Ready to put your forecasts to the test? Explore NBA prediction markets on
Novig today and see how your analysis compares to the crowd.
"""


@pytest.fixture
def seo_validator():
    return SEOValidator()


@pytest.fixture
def mock_engine():
    """Return a RewriterEngine with a mocked Anthropic client."""
    with patch("rewriter.engine.anthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        # Set up the mock response
        mock_message = MagicMock()
        mock_content = MagicMock()
        mock_content.text = MOCK_CLAUDE_RESPONSE
        mock_message.content = [mock_content]
        mock_client.messages.create = AsyncMock(return_value=mock_message)

        engine = RewriterEngine(api_key="test-key")
        yield engine


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_get_template_valid(self):
        for ct in CONTENT_TYPES:
            tmpl = get_template(ct)
            assert isinstance(tmpl, str)
            assert len(tmpl) > 100
            assert "{sport}" in tmpl
            assert "{date}" in tmpl
            assert "{source_data}" in tmpl
            assert "{keywords}" in tmpl

    def test_get_template_invalid(self):
        with pytest.raises(ValueError, match="Unknown content type"):
            get_template("not_real")

    def test_template_contains_novig_voice(self):
        for ct in CONTENT_TYPES:
            tmpl = get_template(ct)
            assert "Novig" in tmpl
            assert "prediction market" in tmpl.lower() or "prediction-market" in tmpl.lower()

    def test_template_output_instructions(self):
        for ct in CONTENT_TYPES:
            tmpl = get_template(ct)
            assert "TITLE:" in tmpl
            assert "META_DESCRIPTION:" in tmpl
            assert "BODY:" in tmpl
            assert "{{novig_internal_link}}" in tmpl


# ---------------------------------------------------------------------------
# SEO validation tests
# ---------------------------------------------------------------------------


class TestSEOValidator:
    def test_passing_article(self, seo_validator: SEOValidator):
        _, _, body = parse_claude_response(MOCK_CLAUDE_RESPONSE)
        result = seo_validator.validate(
            title="NBA Best Bets Today: Top Prediction Market Picks",
            meta_description=(
                "Discover today's top NBA prediction market opportunities. "
                "Our data-driven analysis reveals the best forecasts for "
                "tonight's games on Novig."
            ),
            body=body,
            keywords=["NBA picks", "Novig", "prediction markets"],
        )
        assert result.passed is True
        assert result.score >= 70

    def test_title_too_short(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="NBA Picks",
            meta_description="A" * 150,
            body="## Heading 1\n\n## Heading 2\n\n" + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=[],
        )
        assert any("Title length" in i for i in result.issues)

    def test_title_too_long(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 80,
            meta_description="A" * 150,
            body="## H\n\n## H2\n\n" + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=[],
        )
        assert any("Title length" in i for i in result.issues)

    def test_meta_too_short(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="Too short",
            body="## H\n\n## H2\n\n" + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=[],
        )
        assert any("Meta description length" in i for i in result.issues)

    def test_too_few_headings(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body="## Only one heading\n\n" + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=[],
        )
        assert any("H2 headings" in i for i in result.issues)

    def test_too_few_words(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body="## H1\n\n## H2\n\nShort body.\n{{novig_internal_link}}",
            keywords=[],
        )
        assert any("Word count" in i for i in result.issues)

    def test_missing_keywords(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body="## H1\n\n## H2\n\n" + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=["missing_keyword_xyz"],
        )
        assert any("keyword" in i.lower() for i in result.issues)

    def test_partially_missing_keywords(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body="## H1\n\n## H2\n\nNovig is great " + "word " * 500 + "\n{{novig_internal_link}}",
            keywords=["Novig", "missing_keyword_xyz"],
        )
        assert any("Missing keywords" in i for i in result.issues)

    def test_missing_internal_link(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body="## H1\n\n## H2\n\n" + "word " * 500,
            keywords=[],
        )
        assert any("novig_internal_link" in i for i in result.issues)

    def test_perfect_score(self, seo_validator: SEOValidator):
        body = (
            "## Section One\n\nNovig prediction markets are great.\n\n"
            "## Section Two\n\n" + "word " * 500 + "\n\n{{novig_internal_link}}"
        )
        result = seo_validator.validate(
            title="A" * 50,
            meta_description="A" * 150,
            body=body,
            keywords=["Novig", "prediction markets"],
        )
        assert result.score == 100
        assert result.passed is True
        assert result.issues == []

    def test_seo_result_str(self, seo_validator: SEOValidator):
        result = seo_validator.validate(
            title="Short",
            meta_description="Short",
            body="No headings, too short",
            keywords=["missing"],
        )
        output = str(result)
        assert "SEO" in output
        assert "score" in output


# ---------------------------------------------------------------------------
# Engine / response parsing tests
# ---------------------------------------------------------------------------


class TestParseClaudeResponse:
    def test_full_response(self):
        title, meta, body = parse_claude_response(MOCK_CLAUDE_RESPONSE)
        assert "NBA Best Bets" in title
        assert len(meta) > 50
        assert "## Lakers vs Celtics" in body
        assert "{{novig_internal_link}}" in body

    def test_empty_response(self):
        title, meta, body = parse_claude_response("")
        assert title == ""
        assert meta == ""
        assert body == ""

    def test_partial_response(self):
        partial = "TITLE: My Title\nSome garbage\nBODY:\n# Hello World"
        title, meta, body = parse_claude_response(partial)
        assert title == "My Title"
        assert meta == ""
        assert "Hello World" in body


class TestRewriterEngine:
    @pytest.mark.asyncio
    async def test_rewrite(self, mock_engine: RewriterEngine):
        result = await mock_engine.rewrite(
            source_data=SAMPLE_ARTICLE,
            content_type="best_bets",
            sport="NBA",
            article_date="2026-02-17",
            keywords=["NBA picks"],
        )
        assert "title" in result
        assert "body" in result
        assert "markdown" in result
        assert "seo_result" in result
        assert result["content_type"] == "best_bets"
        assert result["sport"] == "NBA"
        assert "---" in result["markdown"]  # frontmatter

    @pytest.mark.asyncio
    async def test_rewrite_and_save(self, mock_engine: RewriterEngine, tmp_path: Path):
        result = await mock_engine.rewrite_and_save(
            source_data=SAMPLE_ARTICLE,
            content_type="best_bets",
            sport="NBA",
            article_date="2026-02-17",
            keywords=["NBA picks"],
            output_dir=tmp_path,
        )
        assert "output_path" in result
        assert result["output_path"].exists()
        content = result["output_path"].read_text()
        assert "---" in content
        assert "best_bets" in content


# ---------------------------------------------------------------------------
# Pipeline / deduplication tests
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_title_similarity_identical(self):
        assert _title_similarity("NBA Picks Today", "NBA Picks Today") == 1.0

    def test_title_similarity_different(self):
        assert _title_similarity("NBA Picks", "MLB Standings") < 0.5

    def test_title_similarity_similar(self):
        score = _title_similarity(
            "NBA Best Bets for February 17",
            "NBA Best Bets for February 18",
        )
        assert score > 0.85

    def test_is_duplicate_by_url(self):
        article = {"url": "https://example.com/article-1", "title": "Title A"}
        seen = [{"url": "https://example.com/article-1", "title": "Title B"}]
        assert _is_duplicate(article, seen) is True

    def test_is_duplicate_by_title(self):
        article = {"url": "https://a.com/1", "title": "NBA Best Bets for February 17"}
        seen = [{"url": "https://b.com/2", "title": "NBA Best Bets for February 18"}]
        assert _is_duplicate(article, seen) is True

    def test_not_duplicate(self):
        article = {"url": "https://a.com/1", "title": "NBA Analysis"}
        seen = [{"url": "https://b.com/2", "title": "MLB Standings Report"}]
        assert _is_duplicate(article, seen) is False


class TestPipelineProcessor:
    def test_load_raw_articles(self, tmp_path: Path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        articles = [SAMPLE_ARTICLE, {**SAMPLE_ARTICLE, "title": "Another article"}]
        (raw_dir / "rotowire.json").write_text(json.dumps(articles))

        engine = MagicMock(spec=RewriterEngine)
        processor = PipelineProcessor(engine=engine, raw_dir=raw_dir)
        loaded = processor.load_raw_articles()
        assert len(loaded) == 2

    def test_load_single_article(self, tmp_path: Path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "single.json").write_text(json.dumps(SAMPLE_ARTICLE))

        engine = MagicMock(spec=RewriterEngine)
        processor = PipelineProcessor(engine=engine, raw_dir=raw_dir)
        loaded = processor.load_raw_articles()
        assert len(loaded) == 1

    def test_deduplicate(self):
        engine = MagicMock(spec=RewriterEngine)
        processor = PipelineProcessor(engine=engine)

        articles = [
            {"url": "https://a.com/1", "title": "NBA Picks Today"},
            {"url": "https://a.com/1", "title": "NBA Picks Today (dup)"},
            {"url": "https://b.com/2", "title": "MLB Analysis"},
        ]
        result = processor.deduplicate(articles)
        assert len(result) == 2

    def test_load_empty_dir(self, tmp_path: Path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        engine = MagicMock(spec=RewriterEngine)
        processor = PipelineProcessor(engine=engine, raw_dir=raw_dir)
        loaded = processor.load_raw_articles()
        assert len(loaded) == 0

    def test_load_nonexistent_dir(self, tmp_path: Path):
        engine = MagicMock(spec=RewriterEngine)
        processor = PipelineProcessor(
            engine=engine, raw_dir=tmp_path / "does_not_exist"
        )
        loaded = processor.load_raw_articles()
        assert len(loaded) == 0
