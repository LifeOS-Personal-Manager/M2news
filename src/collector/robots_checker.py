from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)


@dataclass
class RobotsInfo:
    parser: RobotFileParser
    available: bool


class RobotsChecker:
    def __init__(self, user_agent: str, timeout: float = 10) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: dict[str, RobotsInfo] = {}

    def can_fetch(self, url: str) -> bool:
        info = self._get_robots_info(url)
        if not info.available:
            return False
        return bool(info.parser.can_fetch(self.user_agent, url))

    def crawl_delay(self, url: str) -> float | None:
        info = self._get_robots_info(url)
        if not info.available:
            return None
        delay = info.parser.crawl_delay(self.user_agent)
        return float(delay) if delay is not None else None

    def _get_robots_info(self, url: str) -> RobotsInfo:
        origin = self._origin(url)
        if origin in self._cache:
            return self._cache[origin]

        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            response = requests.get(
                robots_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                logger.warning("robots.txt unavailable: %s", robots_url)
                info = RobotsInfo(parser=parser, available=False)
            else:
                parser.parse(response.text.splitlines())
                info = RobotsInfo(parser=parser, available=True)
        except requests.RequestException:
            logger.exception("Failed to read robots.txt: %s", robots_url)
            info = RobotsInfo(parser=parser, available=False)

        self._cache[origin] = info
        return info

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")
