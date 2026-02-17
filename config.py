"""Centralized configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Application configuration with sensible defaults.

    All values are read from environment variables at construction time.
    """

    # --- API keys ---
    anthropic_api_key: str = ""
    blog_api_url: str = ""
    blog_api_key: str = ""

    # --- Webflow CMS ---
    webflow_api_token: str = ""
    webflow_collection_id: str = ""

    # --- Scheduling ---
    schedule_hour: int = 6  # 6 AM ET
    schedule_minute: int = 0

    # --- Scraping ---
    rate_limit_delay: float = 2.0  # seconds between requests

    # --- Paths ---
    data_dir: Path = field(default_factory=lambda: Path("data"))
    log_level: str = "INFO"

    # --- Target sites ---
    sites: tuple[str, ...] = ("rotowire", "bettingpros", "oddsshark", "covers")

    @classmethod
    def from_env(cls) -> Config:
        """Build config from environment variables."""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            blog_api_url=os.getenv("BLOG_API_URL", ""),
            blog_api_key=os.getenv("BLOG_API_KEY", ""),
            webflow_api_token=os.getenv("WEBFLOW_API_TOKEN", ""),
            webflow_collection_id=os.getenv("WEBFLOW_COLLECTION_ID", ""),
            schedule_hour=int(os.getenv("SCHEDULE_HOUR", "6")),
            schedule_minute=int(os.getenv("SCHEDULE_MINUTE", "0")),
            rate_limit_delay=float(os.getenv("RATE_LIMIT_DELAY", "2.0")),
            data_dir=Path(os.getenv("DATA_DIR", "data")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def published_dir(self) -> Path:
        return self.data_dir / "published"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
