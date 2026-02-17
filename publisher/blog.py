"""Blog publishing backends.

FilePublisher    — writes final HTML to data/published/{date}/
WebflowPublisher — publishes articles to Webflow CMS via REST API
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import aiofiles
import httpx

logger = logging.getLogger(__name__)


class PublisherBackend(abc.ABC):
    """Abstract interface so we can swap CMS backends later."""

    @abc.abstractmethod
    async def publish(self, article: dict[str, Any]) -> str:
        """Publish a single article and return its identifier."""

    @abc.abstractmethod
    async def is_published(self, slug: str) -> bool:
        """Check whether an article with *slug* has already been published."""


# ---------------------------------------------------------------------------
# Manifest helpers (shared by all backends)
# ---------------------------------------------------------------------------

class Manifest:
    """Thin wrapper around data/published/manifest.json for dedup tracking."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"articles": []}
        async with aiofiles.open(self.path, "r") as f:
            return json.loads(await f.read())

    async def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "w") as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def contains(self, slug: str) -> bool:
        data = await self.load()
        return any(a["slug"] == slug for a in data.get("articles", []))

    async def add(self, entry: dict[str, Any]) -> None:
        data = await self.load()
        data["articles"].append(entry)
        await self.save(data)


# ---------------------------------------------------------------------------
# File-based publisher (default)
# ---------------------------------------------------------------------------

class FilePublisher(PublisherBackend):
    """Saves final HTML articles to data/published/{date}/."""

    def __init__(self, published_dir: Path) -> None:
        self.published_dir = published_dir
        self.manifest = Manifest(published_dir / "manifest.json")

    async def publish(self, article: dict[str, Any]) -> str:
        slug = article["slug"]

        if await self.manifest.contains(slug):
            logger.info("Skipping already-published article: %s", slug)
            return slug

        today = article.get("date", str(date.today()))
        day_dir = self.published_dir / today
        day_dir.mkdir(parents=True, exist_ok=True)

        out_path = day_dir / f"{slug}.html"
        async with aiofiles.open(out_path, "w") as f:
            await f.write(article["html"])

        # Also write RSS snippet alongside the HTML
        if article.get("rss_xml"):
            rss_path = day_dir / f"{slug}.rss.xml"
            async with aiofiles.open(rss_path, "w") as f:
                await f.write(article["rss_xml"])

        await self.manifest.add(
            {
                "slug": slug,
                "title": article.get("title", ""),
                "date": today,
                "path": str(out_path),
            }
        )
        logger.info("Published %s → %s", slug, out_path)
        return slug

    async def is_published(self, slug: str) -> bool:
        return await self.manifest.contains(slug)


# ---------------------------------------------------------------------------
# Webflow CMS publisher
# ---------------------------------------------------------------------------

WEBFLOW_API_BASE = "https://api.webflow.com/v2"

# Webflow rate-limit: back off and retry on 429
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds


def _slugify(title: str) -> str:
    """Generate a URL-safe slug from an article title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60].strip("-")


class WebflowPublisher(PublisherBackend):
    """Publish articles to the Novig blog via the Webflow CMS Collections API.

    Parameters
    ----------
    api_token:
        Webflow API bearer token (from ``WEBFLOW_API_TOKEN`` env var).
    collection_id:
        Webflow CMS collection ID (from ``WEBFLOW_COLLECTION_ID`` env var).
    published_dir:
        Local directory for the dedup manifest.
    live:
        If True, create items as published (isDraft=False).
        Defaults to False (items created as drafts).
    """

    def __init__(
        self,
        api_token: str,
        collection_id: str,
        published_dir: Path,
        live: bool = False,
    ) -> None:
        self.api_token = api_token
        self.collection_id = collection_id
        self.live = live
        self.manifest = Manifest(published_dir / "manifest.json")
        self._client: httpx.AsyncClient | None = None

    # -- HTTP helpers --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers(),
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _post_with_retry(self, url: str, payload: dict) -> httpx.Response:
        """POST with automatic retry on 429 rate-limit responses."""
        client = await self._get_client()
        for attempt in range(1, _MAX_RETRIES + 1):
            resp = await client.post(url, json=payload)
            if resp.status_code != 429:
                return resp
            delay = _RETRY_BASE_DELAY * attempt
            logger.warning(
                "Webflow rate-limited (429), retrying in %.1fs (attempt %d/%d)",
                delay, attempt, _MAX_RETRIES,
            )
            await asyncio.sleep(delay)
        return resp  # return last response even if still 429

    # -- Field mapping -------------------------------------------------------

    def _build_field_data(self, article: dict[str, Any]) -> dict[str, Any]:
        """Map our article dict to Webflow CMS collection field names."""
        title = article.get("title", "Untitled")
        slug = article.get("slug") or _slugify(title)
        return {
            "name": title,
            "slug": slug,
            "post-body": article.get("html", ""),
            "post-summary": article.get("meta", {}).get(
                "meta_description", ""
            ),
            "category": article.get("meta", {}).get("category", "Sports Betting"),
            "date": article.get("date", str(date.today())),
            "author": "Novig AI",
        }

    # -- PublisherBackend implementation -------------------------------------

    async def publish(self, article: dict[str, Any]) -> str:
        slug = article.get("slug") or _slugify(article.get("title", ""))

        if await self.manifest.contains(slug):
            logger.info("Skipping already-published article: %s", slug)
            return slug

        url = f"{WEBFLOW_API_BASE}/collections/{self.collection_id}/items"
        payload = {
            "isArchived": False,
            "isDraft": not self.live,
            "fieldData": self._build_field_data(article),
        }

        resp = await self._post_with_retry(url, payload)

        if resp.status_code in (200, 201, 202):
            webflow_id = resp.json().get("id", "")
            await self.manifest.add(
                {
                    "slug": slug,
                    "title": article.get("title", ""),
                    "date": article.get("date", str(date.today())),
                    "webflow_id": webflow_id,
                    "is_draft": not self.live,
                }
            )
            logger.info(
                "Published to Webflow (%s): %s (id=%s)",
                "live" if self.live else "draft",
                slug,
                webflow_id,
            )
            return slug

        # Handle known error codes
        if resp.status_code == 401:
            logger.error(
                "Webflow auth failed (401) — check WEBFLOW_API_TOKEN"
            )
        elif resp.status_code == 404:
            logger.error(
                "Webflow collection not found (404) — check WEBFLOW_COLLECTION_ID"
            )
        elif resp.status_code == 429:
            logger.error("Webflow rate limit exceeded after %d retries", _MAX_RETRIES)
        else:
            logger.error(
                "Webflow API error %d: %s", resp.status_code, resp.text[:500]
            )
        raise RuntimeError(
            f"Webflow API returned {resp.status_code} for slug '{slug}'"
        )

    async def is_published(self, slug: str) -> bool:
        return await self.manifest.contains(slug)
