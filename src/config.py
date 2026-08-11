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
    {
        "name": "新华网时政",
        "region": "domestic",
        "type": "rss",
        "url": "http://www.xinhuanet.com/politics/news_politics.xml",
        "enabled": True,
    },
    {
        "name": "新华网国际",
        "region": "international",
        "type": "rss",
        "url": "http://www.xinhuanet.com/world/news_world.xml",
        "enabled": True,
    },
    {
        "name": "BBC World",
        "region": "international",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "enabled": True,
    },
    {
        "name": "BBC Business",
        "region": "international",
        "type": "rss",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "enabled": True,
    },
]


def _bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in {None, ""} else default


def _parse_sources(raw_sources: str) -> list[NewsSource]:
    if not raw_sources.strip():
        parsed: Any = DEFAULT_SOURCES
    else:
        try:
            parsed = json.loads(raw_sources)
        except json.JSONDecodeError as exc:
            raise ValueError("NEWS_SOURCES must be a JSON array") from exc

    if not isinstance(parsed, list):
        raise ValueError("NEWS_SOURCES must be a JSON array")

    sources = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each NEWS_SOURCES item must be an object")
        name = str(item.get("name", "")).strip()
        source_type = str(item.get("type", "rss")).strip().lower()
        region = str(item.get("region", "domestic")).strip().lower()
        url = str(item.get("url", "")).strip()
        fallback_url = item.get("fallback_url")
        if source_type not in {"rss", "html"}:
            raise ValueError(f"Unsupported news source type: {source_type}")
        if region not in {"domestic", "international"}:
            raise ValueError(f"Unsupported news source region: {region}")
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
