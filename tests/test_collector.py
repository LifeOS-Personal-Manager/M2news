from __future__ import annotations

from pathlib import Path

import requests

from src.collector.collector import NewsCollector
from src.collector.rss_collector import RssCollector
from src.config import NewsSource, Settings
from src.models import RawNewsItem


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.text = content.decode("utf-8")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def make_settings(tmp_path, sources: list[NewsSource]) -> Settings:
    return Settings(
        news_sources=sources,
        output_dir=tmp_path / "public" / "news",
        timezone="Asia/Shanghai",
        user_agent="test-agent",
        request_timeout=5,
        max_articles_per_source=20,
        base_url="http://localhost",
        openai_api_key=None,
        openai_base_url="https://openrouter.ai/api/v1",
        openai_model="openrouter/free",
        openai_timeout=90,
        enable_llm_analysis=False,
        enable_supabase_backup=False,
        supabase_url=None,
        supabase_service_role_key=None,
        supabase_table_digests="news_digests",
        supabase_table_articles="news_articles",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'news.db'}",
    )


def test_rss_collector_parses_fixture(monkeypatch):
    feed = Path("tests/fixtures/sample_feed.xml").read_bytes()

    def fake_get(*args, **kwargs):
        return FakeResponse(feed)

    monkeypatch.setattr("src.collector.rss_collector.requests.get", fake_get)
    collector = RssCollector(user_agent="test-agent", timeout=5)

    items = collector.collect(
        NewsSource(
            name="测试源",
            region="domestic",
            type="rss",
            url="https://example.com/rss.xml",
        )
    )

    assert len(items) == 2
    assert items[0].title == "第一条新闻"
    assert items[0].source == "测试源"
    assert items[0].region == "domestic"
    assert items[0].published_at is not None


def test_collector_deduplicates_items(monkeypatch, tmp_path):
    settings = make_settings(
        tmp_path,
        [
            NewsSource(name="A", region="domestic", type="rss", url="https://a.test"),
            NewsSource(name="B", region="domestic", type="rss", url="https://b.test"),
        ],
    )
    collector = NewsCollector(settings)

    def fake_collect(source, date=None):
        return [
            RawNewsItem.create(
                title="Same",
                url="https://example.com/news/1?utm_source=a",
                summary="",
                source=source.name,
                region=source.region,
            )
        ]

    monkeypatch.setattr(collector.rss_collector, "collect", fake_collect)
    monkeypatch.setattr(collector, "_wait_for_domain", lambda *args, **kwargs: None)

    items = collector.collect_all()

    assert len(items) == 1
