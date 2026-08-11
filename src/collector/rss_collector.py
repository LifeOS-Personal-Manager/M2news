from __future__ import annotations

import logging
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

from src.config import NewsSource
from src.models import RawNewsItem

logger = logging.getLogger(__name__)


class RssCollector:
    def __init__(
        self,
        user_agent: str,
        timeout: float,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def collect(self, source: NewsSource, date: str | None = None) -> list[RawNewsItem]:
        content = self._fetch(source.url)
        feed = feedparser.parse(content)
        if getattr(feed, "bozo", False):
            logger.warning("RSS parser reported a problem for %s", source.url)

        items: list[RawNewsItem] = []
        for entry in feed.entries:
            link = str(entry.get("link", "")).strip()
            title = str(entry.get("title", "")).strip()
            if not link or not title:
                continue
            summary = str(
                entry.get("summary")
                or entry.get("description")
                or entry.get("subtitle")
                or ""
            )
            items.append(
                RawNewsItem.create(
                    title=title,
                    url=link,
                    summary=summary,
                    source=source.name,
                    region=source.region,
                    published_at=_entry_published_at(entry),
                )
            )
        return items

    def _fetch(self, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.content
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_base * (2 ** (attempt - 1)))
        raise RuntimeError(f"Failed to fetch RSS after retries: {url}") from last_error


def _entry_published_at(entry: Any) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).isoformat()
        except (TypeError, ValueError, IndexError):
            try:
                return datetime.fromisoformat(str(value)).isoformat()
            except ValueError:
                return str(value)
    return None
