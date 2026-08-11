from __future__ import annotations

import logging
import time

import requests
from bs4 import BeautifulSoup

from src.collector.robots_checker import RobotsChecker
from src.config import NewsSource
from src.models import RawNewsItem

logger = logging.getLogger(__name__)


class WebCollector:
    def __init__(
        self,
        robots_checker: RobotsChecker,
        user_agent: str,
        timeout: float,
        max_retries: int = 3,
        backoff_base: float = 0.5,
    ) -> None:
        self.robots_checker = robots_checker
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def collect(
        self,
        source: NewsSource,
        date: str | None = None,
    ) -> list[RawNewsItem]:
        if not self.robots_checker.can_fetch(source.url):
            logger.warning("Skipping HTML source disallowed by robots: %s", source.url)
            return []
        html = self._fetch(source.url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        items = []
        seen_links = set()
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            url = str(anchor["href"]).strip()
            if not title or not url.startswith(("http://", "https://")):
                continue
            if url in seen_links:
                continue
            seen_links.add(url)
            items.append(
                RawNewsItem.create(
                    title=title,
                    source=source.name,
                    url=url,
                    region=source.region,
                    summary=_nearby_summary(anchor),
                )
            )
        return items

    def _fetch(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                if _looks_like_login_or_challenge(response.text):
                    logger.warning("Skipping gated/challenged page: %s", url)
                    return ""
                return response.text
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_base * (2 ** (attempt - 1)))
        raise RuntimeError(f"Failed to fetch HTML after retries: {url}") from last_error


def _nearby_summary(anchor: object) -> str:
    parent = getattr(anchor, "parent", None)
    if parent is None:
        return ""
    return parent.get_text(" ", strip=True)[:300]


def _looks_like_login_or_challenge(html: str) -> bool:
    lowered = html.lower()
    markers = (
        "captcha",
        "cloudflare",
        "cf-challenge",
        "login",
        "sign in",
        "登录",
        "验证码",
    )
    return any(marker in lowered for marker in markers)
