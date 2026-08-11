from __future__ import annotations

import logging
from typing import Any

from src.config import Settings
from src.llm.client import LLMClient
from src.llm.prompts import SYSTEM_PROMPT, build_digest_prompt
from src.models import CATEGORIES, REGIONS, DailyDigest, RawNewsItem, empty_sections
from src.models import utc_now_iso

logger = logging.getLogger(__name__)


class DigestAnalyzer:
    def __init__(
        self,
        settings: Settings,
        client: LLMClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or LLMClient(settings)

    def analyze(
        self,
        *,
        target_date: str,
        period_from: str,
        period_to: str,
        items: list[RawNewsItem],
    ) -> DailyDigest:
        if not items:
            return empty_digest(target_date, period_from, period_to)
        if not self.settings.enable_llm_analysis or not self.settings.openai_api_key:
            return fallback_digest(target_date, period_from, period_to, items)
        try:
            payload = self.client.chat_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=build_digest_prompt(
                    target_date=target_date,
                    period_from=period_from,
                    period_to=period_to,
                    items=items,
                ),
            )
            return normalize_digest(payload, target_date, period_from, period_to)
        except Exception:
            logger.exception("LLM digest analysis failed; using fallback digest")
            return fallback_digest(target_date, period_from, period_to, items)


def empty_digest(target_date: str, period_from: str, period_to: str) -> DailyDigest:
    return DailyDigest(
        date=target_date,
        period={"from": period_from, "to": period_to},
        sections=empty_sections(),
        top_highlights=["前日及当日暂无可整理新闻。"],
        generated_at=utc_now_iso(),
    )


def fallback_digest(
    target_date: str,
    period_from: str,
    period_to: str,
    items: list[RawNewsItem],
) -> DailyDigest:
    sections = empty_sections()
    for item in items:
        category = guess_category(item)
        article = {
            "title": item.title,
            "source": item.source,
            "url": item.url,
            "published_at": item.published_at,
            "category": category,
            "region": item.region,
            "summary": item.summary or item.title,
            "impact": "信息不足，暂不解读",
            "why_it_matters": "该资讯来自公开来源，已纳入对应栏目供后续阅读判断。",
            "confidence": 0.5,
            "hash": item.hash,
            "references": [
                {"source": item.source, "url": item.url, "title": item.title}
            ],
        }
        sections[item.region][category].append(article)
    return DailyDigest(
        date=target_date,
        period={"from": period_from, "to": period_to},
        sections=sections,
        top_highlights=[item.title for item in items[:5]],
        generated_at=utc_now_iso(),
    )


def normalize_digest(
    payload: dict[str, Any],
    target_date: str,
    period_from: str,
    period_to: str,
) -> DailyDigest:
    sections = empty_sections()
    raw_sections = payload.get("sections", {})
    if isinstance(raw_sections, dict):
        for region in REGIONS:
            raw_region = raw_sections.get(region, {})
            if not isinstance(raw_region, dict):
                continue
            for category in CATEGORIES:
                raw_items = raw_region.get(category, [])
                if isinstance(raw_items, list):
                    sections[region][category] = [
                        normalize_article(item, region, category)
                        for item in raw_items
                        if isinstance(item, dict)
                    ]
    highlights = payload.get("top_highlights", [])
    if not isinstance(highlights, list):
        highlights = []
    return DailyDigest(
        date=str(payload.get("date") or target_date),
        period={"from": period_from, "to": period_to},
        sections=sections,
        top_highlights=[str(item) for item in highlights[:8]],
        generated_at=str(payload.get("generated_at") or utc_now_iso()),
    )


def normalize_article(
    item: dict[str, Any],
    region: str,
    category: str,
) -> dict[str, Any]:
    confidence = item.get("confidence", 0.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    references = item.get("references", [])
    if not isinstance(references, list):
        references = []
    return {
        "title": str(item.get("title", "")),
        "source": str(item.get("source", "")),
        "url": str(item.get("url", "")),
        "published_at": item.get("published_at"),
        "category": str(item.get("category") or category),
        "region": str(item.get("region") or region),
        "summary": str(item.get("summary", "")),
        "impact": str(item.get("impact", "信息不足，暂不解读")),
        "why_it_matters": str(item.get("why_it_matters", "信息不足，暂不解读")),
        "confidence": confidence,
        "hash": str(item.get("hash", "")),
        "references": [
            {
                "source": str(ref.get("source", "")),
                "url": str(ref.get("url", "")),
                "title": str(ref.get("title", "")),
            }
            for ref in references
            if isinstance(ref, dict)
        ],
    }


def guess_category(item: RawNewsItem) -> str:
    text = f"{item.source} {item.title} {item.summary}".lower()
    rules = (
        ("economy_finance", ("财经", "金融", "经济", "市场", "股", "央行", "business")),
        ("society_welfare", ("民生", "社会", "保障", "医疗", "教育", "就业", "health")),
        ("industry", ("产业", "行业", "科技", "能源", "汽车", "ai", "芯片", "tech")),
        ("culture_sports", ("文化", "体育", "娱乐", "赛事", "电影", "sports")),
        ("politics", ("政治", "时政", "政府", "外交", "选举", "policy")),
    )
    for category, markers in rules:
        if any(marker in text for marker in markers):
            return category
    return "politics"
