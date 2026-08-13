from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class NewsSource:
    name: str
    region: str
    url: str
    type: str = "rss"
    enabled: bool = True
    fallback_url: str | None = None
    weight: float = 0.5
    time_window_hours: int = 24
    parse_mode: str = "rss"
    category: str = ""


@dataclass(frozen=True)
class Settings:
    news_sources: list[NewsSource]
    output_dir: Path
    timezone: str
    user_agent: str
    request_timeout: float
    max_articles_per_source: int
    base_url: str
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    openai_timeout: float
    enable_llm_analysis: bool
    enable_supabase_backup: bool
    supabase_url: str | None
    supabase_service_role_key: str | None
    supabase_table_digests: str
    supabase_table_articles: str
    data_dir: Path
    database_url: str

    @property
    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
        raw_path = self.database_url.removeprefix("sqlite:///")
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path


DEFAULT_SOURCES = [
    {"name": "微博热搜", "region": "domestic", "type": "hotlist", "url": "https://rsshub.app/weibo/search/hot", "enabled": True, "weight": 1.0, "time_window_hours": 24, "parse_mode": "rsshub", "category": "热点"},
    {"name": "知乎热榜", "region": "domestic", "type": "hotlist", "url": "https://rsshub.app/zhihu/hotlist", "enabled": True, "weight": 1.0, "time_window_hours": 24, "parse_mode": "rsshub", "category": "热点"},
    {"name": "百度热点", "region": "domestic", "type": "hotlist", "url": "https://rsshub.app/baidu/bulletins", "enabled": True, "weight": 1.0, "time_window_hours": 24, "parse_mode": "rsshub", "category": "热点"},
    {"name": "GitHub Trending", "region": "international", "type": "hotlist", "url": "https://rsshub.app/github/trending/daily/any", "enabled": True, "weight": 1.0, "time_window_hours": 24, "parse_mode": "rsshub", "category": "科技"},
    {"name": "新华社最新", "region": "domestic", "type": "news", "url": "http://www.news.cn/politics/news_politics.xml", "enabled": True, "weight": 0.8, "time_window_hours": 12, "parse_mode": "rss", "category": "政治"},
    {"name": "央视新闻", "region": "domestic", "type": "news", "url": "https://news.cctv.com/rss/index.xml", "enabled": True, "weight": 0.8, "time_window_hours": 12, "parse_mode": "rss", "category": "政治"},
    {"name": "中新社", "region": "domestic", "type": "news", "url": "https://www.chinanews.com.cn/rss/scroll-news.xml", "enabled": True, "weight": 0.8, "time_window_hours": 12, "parse_mode": "rss", "category": "政治"},
    {"name": "Reuters Asia", "region": "international", "type": "news", "url": "https://feeds.reuters.com/reuters/asiaNews", "enabled": True, "weight": 0.8, "time_window_hours": 12, "parse_mode": "rss", "category": "国际"},
    {"name": "AP Top News", "region": "international", "type": "news", "url": "https://feeds.apnews.com/rss/apf-topnews", "enabled": True, "weight": 0.8, "time_window_hours": 12, "parse_mode": "rss", "category": "国际"},
    {"name": "36氪最新", "region": "domestic", "type": "news", "url": "https://rsshub.app/36kr/news/latest", "enabled": True, "weight": 0.6, "time_window_hours": 24, "parse_mode": "rsshub", "category": "科技"},
    {"name": "MIT Tech Review", "region": "international", "type": "news", "url": "https://www.technologyreview.com/feed/", "enabled": True, "weight": 0.6, "time_window_hours": 24, "parse_mode": "rss", "category": "科技"},
    {"name": "财新最新", "region": "domestic", "type": "news", "url": "https://rsshub.app/caixin/latest", "enabled": True, "weight": 0.6, "time_window_hours": 24, "parse_mode": "rsshub", "category": "财经"},
    {"name": "WSJ Markets", "region": "international", "type": "news", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "enabled": True, "weight": 0.6, "time_window_hours": 24, "parse_mode": "rss", "category": "财经"},
    {"name": "Foreign Affairs", "region": "international", "type": "news", "url": "https://rsshub.app/foreignaffairs/theater", "enabled": True, "weight": 0.6, "time_window_hours": 48, "parse_mode": "rsshub", "category": "地缘"},
    {"name": "新华网国际", "region": "international", "type": "news", "url": "http://www.xinhuanet.com/world/news_world.xml", "enabled": True, "weight": 0.4, "time_window_hours": 6, "parse_mode": "rss", "category": "国际"},
    {"name": "BBC World", "region": "international", "type": "news", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "enabled": True, "weight": 0.4, "time_window_hours": 6, "parse_mode": "rss", "category": "国际"},
]


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in {None, ""} else default


def _load_feeds_json() -> list[dict[str, Any]] | None:
    """Try to load feeds.json from the project root."""
    candidates = [
        Path.cwd() / "feeds.json",
        Path(__file__).resolve().parent.parent / "feeds.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sources = data.get("sources", data) if isinstance(data, dict) else data
                if isinstance(sources, list):
                    return sources
            except (json.JSONDecodeError, OSError):
                pass
    return None


def _parse_sources(raw_sources: str) -> list[NewsSource]:
    # Priority: NEWS_SOURCES env var > feeds.json > DEFAULT_SOURCES
    if raw_sources.strip():
        try:
            parsed: Any = json.loads(raw_sources)
        except json.JSONDecodeError as exc:
            raise ValueError("NEWS_SOURCES must be a JSON array") from exc
    else:
        feeds = _load_feeds_json()
        parsed = feeds if feeds is not None else DEFAULT_SOURCES

    if not isinstance(parsed, list):
        raise ValueError("News sources must be a JSON array")

    sources = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each news source item must be an object")
        name = str(item.get("name", "")).strip()
        source_type = str(item.get("type", "rss")).strip().lower()
        region = str(item.get("region", "domestic")).strip().lower()
        url = str(item.get("url", "")).strip()
        fallback_url = item.get("fallback_url")
        if not name or not url:
            raise ValueError("Each source must include name and url")
        sources.append(
            NewsSource(
                name=name,
                region=region,
                type=source_type,
                url=url,
                enabled=bool(item.get("enabled", True)),
                fallback_url=str(fallback_url).strip() if fallback_url else None,
                weight=float(item.get("weight", 0.5)),
                time_window_hours=int(item.get("time_window_hours", 24)),
                parse_mode=str(item.get("parse_mode", "rss")).strip().lower(),
                category=str(item.get("category", "")).strip(),
            )
        )
    return sources


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    load_dotenv(env_file)
    output_dir = Path(_env("OUTPUT_DIR", _env("DATA_DIR", "public/news")))
    openai_api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    return Settings(
        news_sources=_parse_sources(os.getenv("NEWS_SOURCES", "")),
        output_dir=output_dir,
        timezone=_env("TIMEZONE", "Asia/Shanghai"),
        user_agent=_env("USER_AGENT", "PersonalNewsDigestBot/1.0"),
        request_timeout=float(_env("REQUEST_TIMEOUT", "15")),
        max_articles_per_source=int(_env("MAX_ARTICLES_PER_SOURCE", "20")),
        base_url=_env("BASE_URL", ""),
        openai_api_key=openai_api_key or None,
        openai_base_url=_env(
            "OPENAI_BASE_URL",
            _env("DEEPSEEK_BASE_URL", "https://api.openai.com/v1"),
        ),
        openai_model=_env(
            "OPENAI_MODEL",
            _env("DEEPSEEK_MODEL", "openrouter/free"),
        ),
        openai_timeout=float(_env("OPENAI_TIMEOUT", _env("DEEPSEEK_TIMEOUT", "90"))),
        enable_llm_analysis=_bool_env("ENABLE_LLM_ANALYSIS", True),
        enable_supabase_backup=_bool_env("ENABLE_SUPABASE_BACKUP", False),
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None,
        supabase_table_digests=os.getenv("SUPABASE_TABLE_DIGESTS", "news_digests"),
        supabase_table_articles=os.getenv("SUPABASE_TABLE_ARTICLES", "news_articles"),
        data_dir=Path(_env("DATA_DIR", "data")),
        database_url=_env("DATABASE_URL", "sqlite:///data/news.db"),
    )
