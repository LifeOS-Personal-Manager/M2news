from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.main import run

logger = logging.getLogger(__name__)


class DigestJob:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_once(self) -> str:
        return run(self.settings)

    def run_safely(self) -> None:
        try:
            self.run_once()
        except Exception:
            logger.exception("Digest job failed")


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    job = DigestJob(settings)
    scheduler.add_job(
        job.run_safely,
        CronTrigger(hour=8, minute=0, timezone=settings.timezone),
        id="daily_news_digest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
