from __future__ import annotations

from src.llm.digest_analyzer import DigestAnalyzer
from src.llm.prompts import build_digest_prompt
from src.models import RawNewsItem
from tests.test_collector import make_settings


def test_prompt_contains_required_structure():
    item = RawNewsItem.create(
        title="国际经济新闻",
        source="BBC World",
        url="https://example.com/world-business",
        region="international",
        summary="摘要",
    )

    prompt = build_digest_prompt(
        target_date="2026-08-11",
        period_from="2026-08-10",
        period_to="2026-08-11",
        items=[item],
    )

    assert "international" in prompt
    assert "domestic" in prompt
    assert "economy_finance" in prompt
    assert "严格 JSON" in prompt


def test_analyzer_falls_back_without_api_key(tmp_path):
    settings = make_settings(tmp_path, [])
    item = RawNewsItem.create(
        title="国际经济新闻",
        url="https://example.com/world-business",
        summary="摘要",
        source="BBC World",
        region="international",
    )

    digest = DigestAnalyzer(settings).analyze(
        target_date="2026-08-11",
        period_from="2026-08-10",
        period_to="2026-08-11",
        items=[item],
    )

    items = digest.sections["international"]["economy_finance"]
    assert items[0]["title"] == "国际经济新闻"
