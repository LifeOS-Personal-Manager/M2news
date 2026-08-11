from __future__ import annotations

import json

from src.generator.digest_generator import DigestGenerator
from src.models import DailyDigest, empty_sections, utc_now_iso
from src.storage.file_store import FileStore


def test_generator_writes_json_html_and_latest(tmp_path):
    sections = empty_sections()
    sections["domestic"]["politics"].append(
        {
            "title": "新闻标题",
            "source": "测试源",
            "url": "https://example.com/news/1",
            "published_at": "2026-08-11T08:00:00+08:00",
            "category": "politics",
            "region": "domestic",
            "summary": "新闻摘要",
            "impact": "影响解读",
            "why_it_matters": "值得关注",
            "confidence": 0.8,
            "hash": "abc",
            "references": [
                {
                    "source": "测试源",
                    "url": "https://example.com/news/1",
                    "title": "新闻标题",
                }
            ],
        }
    )
    digest = DailyDigest(
        date="2026-08-11",
        period={"from": "2026-08-10", "to": "2026-08-11"},
        sections=sections,
        top_highlights=["新闻标题"],
        generated_at=utc_now_iso(),
    )
    generator = DigestGenerator(FileStore(tmp_path))

    json_path, html_path = generator.generate(digest)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    assert payload["sections"]["domestic"]["politics"][0]["title"] == "新闻标题"
    assert "2026年8月11日 前日及当日要闻解读" in html
    assert "新闻标题" in html
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest.html").exists()
