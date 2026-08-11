from __future__ import annotations

import json

from src.models import CATEGORIES, REGIONS, RawNewsItem

SYSTEM_PROMPT = """你是严谨、克制的中文新闻分析师。
你只允许基于用户提供的新闻条目进行整理和解读，不得编造新闻、数据、背景或结论。
如果信息不足，必须写“信息不足，暂不解读”。
你必须保留原始来源链接。同一事件的多来源报道可以合并为一条，并在 references 中保留来源。
输出必须是严格 JSON，不要输出 Markdown，不要输出解释文字。"""


JSON_CONTRACT = {
    "date": "YYYY-MM-DD",
    "period": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
    "sections": {
        region: {category: [] for category in CATEGORIES} for region in REGIONS
    },
    "top_highlights": [],
    "generated_at": "ISO8601",
}


def build_digest_prompt(
    *,
    target_date: str,
    period_from: str,
    period_to: str,
    items: list[RawNewsItem],
) -> str:
    payload = {
        "date": target_date,
        "period": {"from": period_from, "to": period_to},
        "allowed_regions": list(REGIONS),
        "allowed_categories": list(CATEGORIES),
        "required_article_fields": [
            "title",
            "source",
            "url",
            "published_at",
            "category",
            "region",
            "summary",
            "impact",
            "why_it_matters",
            "confidence",
            "hash",
            "references",
        ],
        "raw_items": [item.to_dict() for item in items],
    }
    return (
        "请将 raw_items 整理为前日及当日要闻。要求：\n"
        "1. 输出中文。\n"
        "2. 按 international/domestic 两大板块和五个固定分类输出。\n"
        "3. 对新闻去重，同一事件多来源合并为一条。\n"
        "4. 每条摘要 100-200 字；impact 写影响；why_it_matters 写值得关注的原因。\n"
        "5. 重要新闻排在各分类前面，top_highlights 给出 3-8 条全局重点。\n"
        "6. 不得新增 raw_items 中不存在的新闻。\n"
        "7. 信息不足时，对 impact 或 why_it_matters 写“信息不足，暂不解读”。\n"
        "8. confidence 为 0 到 1 的数字。\n\n"
        "必须输出与此结构兼容的严格 JSON：\n"
        f"{json.dumps(JSON_CONTRACT, ensure_ascii=False)}\n\n"
        "输入数据：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
