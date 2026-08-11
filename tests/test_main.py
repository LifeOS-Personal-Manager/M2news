from __future__ import annotations

import json

from src.config import NewsSource
from src.main import run
from src.models import RawNewsItem
from tests.test_collector import make_settings


def test_main_generates_static_digest(monkeypatch, tmp_path):
    settings = make_settings(
        tmp_path,
        [
            NewsSource(
                name="测试源",
                region="domestic",
                type="rss",
                url="https://example.com/rss.xml",
            )
        ],
    )

    def fake_collect_all(self, date=None):
        return [
            RawNewsItem.create(
                title="国内政治新闻",
                source="测试源",
                url="https://example.com/news/1",
                region="domestic",
                summary="摘要",
            )
        ]

    monkeypatch.setattr(
        "src.collector.collector.NewsCollector.collect_all", fake_collect_all
    )

    run(settings)

    latest = settings.output_dir / "latest.json"
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["sections"]["domestic"]["politics"][0]["title"] == "国内政治新闻"
