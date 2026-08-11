from __future__ import annotations

import logging
import time

import requests
from bs4 import BeautifulSoup

from src.config import NewsSource
from src.collector.robots_checker import RobotsChecker
from src.models import NewsItem

logger = logging.getLogger(__name__)


class HtmlCollector:
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

    def collect(self, source: NewsSource, date: str) -> list[NewsItem]:
        if not self.robots_checker.can_fetch(source.url):
            logger.warning("Skipping HTML source disallowed by robots: %s", source.url)
            return []

        response_text = self._fetch(source.url)
        soup = BeautifulSoup(response_text, "html.parser")
        items = []
        seen_links = set()
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            link = str(anchor["href"]).strip()
            if not title or not link.startswith(("http://", "https://")):
                continue
            if link in seen_links:
                continue
            seen_links.add(link)
            summary = _nearby_summary(anchor)
            items.append(
                NewsItem.create(
                    title=title,
                    link=link,
                    summary=summary,
                    source=source.name,
                    date=date,
                    published_at=None,
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
                    logger.warning(
                        "Skipping page that looks gated or challenged: %s", url
                    )
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
    text = parent.get_text(" ", strip=True)
    return text[:300]


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
