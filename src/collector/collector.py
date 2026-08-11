from __future__ import annotations

import logging
import time
from collections import defaultdict
from urllib.parse import urlsplit

from src.config import NewsSource, Settings
from src.collector.robots_checker import RobotsChecker
from src.collector.rss_collector import RssCollector
from src.collector.web_collector import WebCollector
from src.models import RawNewsItem

logger = logging.getLogger(__name__)


class NewsCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.robots_checker = RobotsChecker(
            user_agent=settings.user_agent,
            timeout=settings.request_timeout,
        )
        self.rss_collector = RssCollector(
            user_agent=settings.user_agent,
            timeout=settings.request_timeout,
        )
        self.web_collector = WebCollector(
            robots_checker=self.robots_checker,
            user_agent=settings.user_agent,
            timeout=settings.request_timeout,
        )
        self._last_request_at: dict[str, float] = defaultdict(float)

    def collect_all(self, date: str | None = None) -> list[RawNewsItem]:
        collected = []
        for source in self.settings.news_sources:
            if not source.enabled:
                continue
            try:
                collected.extend(
                    self._collect_source(source, date)[
                        : self.settings.max_articles_per_source
                    ]
                )
            except Exception:
                logger.exception("Failed to collect source: %s", source.name)
        return _dedupe_items(collected)

    def _collect_source(
        self,
        source: NewsSource,
        date: str | None,
    ) -> list[RawNewsItem]:
        if source.type == "rss":
            self._wait_for_domain(source.url, minimum_delay=1.0)
            try:
                items = self.rss_collector.collect(source, date)
                if items:
                    return items
            except Exception:
                logger.exception("RSS source failed: %s", source.name)
            if source.fallback_url:
                fallback = NewsSource(
                    name=source.name,
                    region=source.region,
                    type="html",
                    url=source.fallback_url,
                )
                return self._collect_web(fallback, date)
            return []

        return self._collect_web(source, date)

    def _collect_web(self, source: NewsSource, date: str | None) -> list[RawNewsItem]:
        delay = max(1.0, self.robots_checker.crawl_delay(source.url) or 0.0)
        self._wait_for_domain(source.url, minimum_delay=delay)
        return self.web_collector.collect(source, date)

    def _wait_for_domain(self, url: str, minimum_delay: float) -> None:
        domain = urlsplit(url).netloc.lower()
        elapsed = time.monotonic() - self._last_request_at[domain]
        if elapsed < minimum_delay:
            time.sleep(minimum_delay - elapsed)
        self._last_request_at[domain] = time.monotonic()


def _dedupe_items(items: list[RawNewsItem]) -> list[RawNewsItem]:
    seen = set()
    result = []
    for item in items:
        if item.hash in seen:
            continue
        seen.add(item.hash)
        result.append(item)
    return result
