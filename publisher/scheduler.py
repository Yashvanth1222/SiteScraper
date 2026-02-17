"""APScheduler-based daily pipeline scheduler."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """Schedule and execute the daily content pipeline."""

    def __init__(
        self,
        run_pipeline_fn,
        hour: int = 6,
        minute: int = 0,
        timezone: str = "US/Eastern",
        log_dir: Path | None = None,
    ) -> None:
        self._run_pipeline = run_pipeline_fn
        self._hour = hour
        self._minute = minute
        self._timezone = timezone
        self._log_dir = log_dir
        self._scheduler: AsyncIOScheduler | None = None

    async def _wrapped_run(self) -> None:
        """Execute the pipeline, logging success or failure."""
        logger.info("Scheduled pipeline run starting")
        try:
            await self._run_pipeline()
            logger.info("Scheduled pipeline run completed successfully")
        except Exception:
            logger.exception("Scheduled pipeline run failed")

    def start(self) -> None:
        """Start the scheduler (blocks via asyncio event loop)."""
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

        self._scheduler = AsyncIOScheduler()
        trigger = CronTrigger(
            hour=self._hour,
            minute=self._minute,
            timezone=self._timezone,
        )
        self._scheduler.add_job(self._wrapped_run, trigger, id="daily_pipeline")
        self._scheduler.start()
        logger.info(
            "Scheduler started — pipeline will run daily at %02d:%02d %s",
            self._hour,
            self._minute,
            self._timezone,
        )

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")

    def run_blocking(self) -> None:
        """Start scheduler and block forever (for CLI --schedule mode)."""
        self.start()
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            self.stop()
