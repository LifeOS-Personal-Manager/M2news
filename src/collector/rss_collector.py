from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import requests

from src.config import NewsSource
from src.models import RawNewsItem

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"s+")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _entry_published_at(entry: Any) -> str | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            dt = parsedate_to_datetime(value)
            return dt.isoformat()
        except (TypeError, ValueError, IndexError):
            try:
                return datetime.fromisoformat(str(value)).isoformat()
            except ValueError:
                return str(value)
    return None


def _entry_datetime(entry: Any) -> datetime | None:
    """Parse entry publication time as a timezone-aware datetime."""
    iso = _entry_published_at(entry)
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


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

    def collect(
        self,
        source: NewsSource,
        date: str | None = None,
    ) -> list[RawNewsItem]:
        content = self._fetch(source.url)
        feed = feedparser.parse(content)
        if getattr(feed, "bozo", False):
            logger.warning("RSS parser reported a problem for %s", source.url)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=source.time_window_hours)

        items: list[RawNewsItem] = []
        for entry in feed.entries:
            link = str(entry.get("link", "")).strip()
            title = _strip_html(str(entry.get("title", "")).strip())
            if not link or not title:
                continue

            published_at = _entry_published_at(entry)
            entry_dt = _entry_datetime(entry)

            # Time window filtering: skip entries older than the cutoff
            if entry_dt and entry_dt < cutoff:
                logger.debug(
                    "Skipping old entry from %s: %s (published %s, cutoff %s)",
                    source.name, title[:40], entry_dt.isoformat(), cutoff.isoformat(),
                )
                continue

            raw_summary = (
                entry.get("summary")
                or entry.get("description")
                or entry.get("subtitle")
                or ""
            )
            summary = _strip_html(str(raw_summary))[:500]

            items.append(
                RawNewsItem.create(
                    title=title,
                    url=link,
                    summary=summary,
                    source=source.name,
                    region=source.region,
                    published_at=published_at,
                )
            )

        logger.info(
            "Collected %d items from %s (time_window=%dh, cutoff=%s)",
            len(items), source.name, source.time_window_hours, cutoff.isoformat(),
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
