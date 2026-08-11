from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from src.config import Settings
from src.models import NewsItem

logger = logging.getLogger(__name__)

DOMAINS = ("domestic", "international")
CATEGORIES = (
    "politics",
    "economy_finance",
    "society_welfare",
    "industry",
    "culture_sports",
)

DOMAIN_LABELS = {
    "domestic": "国内新闻",
    "international": "国际新闻",
}

CATEGORY_LABELS = {
    "politics": "政治发展",
    "economy_finance": "经济金融",
    "society_welfare": "社会民生保障",
    "industry": "产业行业",
    "culture_sports": "文化体育",
}


@dataclass(frozen=True)
class DigestWindow:
    previous_date: str
    current_date: str


class DeepSeekAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze(
        self,
        *,
        window: DigestWindow,
        previous_items: list[NewsItem],
        current_items: list[NewsItem],
    ) -> dict[str, Any]:
        base = empty_analysis(window)
        all_items = previous_items + current_items
        if not all_items:
            base["executive_summary"] = "前一日及当日暂无可分析新闻。"
            return base

        if not self.settings.enable_llm_analysis or not self.settings.openai_api_key:
            return heuristic_analysis(window, previous_items, current_items)

        try:
            return self._call_deepseek(window, previous_items, current_items)
        except Exception:
            logger.exception(
                "DeepSeek analysis failed; falling back to heuristic output"
            )
            return heuristic_analysis(window, previous_items, current_items)

    def _call_deepseek(
        self,
        window: DigestWindow,
        previous_items: list[NewsItem],
        current_items: list[NewsItem],
    ) -> dict[str, Any]:
        payload = {
            "model": self.settings.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的中文新闻分析师。只基于用户提供的新闻条目"
                        "进行归类和解读，不编造事实。输出必须是合法 JSON。"
                    ),
                },
                {
                    "role": "user",
                    "content": _build_prompt(window, previous_items, current_items),
                },
            ],
            "thinking": {"type": "disabled"},
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.settings.openai_timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return normalize_analysis(parsed, window)


def empty_analysis(window: DigestWindow) -> dict[str, Any]:
    return {
        "period": {
            "previous_date": window.previous_date,
            "current_date": window.current_date,
        },
        "executive_summary": "",
        "sections": {
            domain: {
                "label": DOMAIN_LABELS[domain],
                "categories": {
                    category: {
                        "label": CATEGORY_LABELS[category],
                        "items": [],
                    }
                    for category in CATEGORIES
                },
            }
            for domain in DOMAINS
        },
    }


def heuristic_analysis(
    window: DigestWindow,
    previous_items: list[NewsItem],
    current_items: list[NewsItem],
) -> dict[str, Any]:
    analysis = empty_analysis(window)
    analysis["executive_summary"] = (
        "DeepSeek 未配置或暂不可用，以下为基于标题、来源和摘要的基础归类；"
        "配置 DEEPSEEK_API_KEY 后会生成更完整的影响与意义解读。"
    )
    for item in previous_items + current_items:
        domain = _guess_domain(item)
        category = _guess_category(item)
        analysis["sections"][domain]["categories"][category]["items"].append(
            {
                "date": item.date,
                "title": item.title,
                "source": item.source,
                "link": item.link,
                "summary": item.summary,
                "impact": "待 DeepSeek 结合上下文进一步分析。",
                "significance": "该资讯已纳入对应栏目，供后续趋势研判参考。",
            }
        )
    return analysis


def normalize_analysis(parsed: dict[str, Any], window: DigestWindow) -> dict[str, Any]:
    normalized = empty_analysis(window)
    normalized["executive_summary"] = str(parsed.get("executive_summary", "")).strip()
    parsed_sections = parsed.get("sections", {})
    if not isinstance(parsed_sections, dict):
        return normalized

    for domain in DOMAINS:
        parsed_domain = parsed_sections.get(domain, {})
        parsed_categories = (
            parsed_domain.get("categories", {})
            if isinstance(parsed_domain, dict)
            else {}
        )
        for category in CATEGORIES:
            parsed_category = parsed_categories.get(category, {})
            items = (
                parsed_category.get("items", [])
                if isinstance(parsed_category, dict)
                else []
            )
            if isinstance(items, list):
                normalized["sections"][domain]["categories"][category]["items"] = [
                    _normalize_analysis_item(item)
                    for item in items
                    if isinstance(item, dict)
                ]
    return normalized


def _normalize_analysis_item(item: dict[str, Any]) -> dict[str, str]:
    return {
        "date": str(item.get("date", "")),
        "title": str(item.get("title", "")),
        "source": str(item.get("source", "")),
        "link": str(item.get("link", "")),
        "summary": str(item.get("summary", "")),
        "impact": str(item.get("impact", "")),
        "significance": str(item.get("significance", "")),
    }


def _build_prompt(
    window: DigestWindow,
    previous_items: list[NewsItem],
    current_items: list[NewsItem],
) -> str:
    news_payload = {
        "previous_date": window.previous_date,
        "current_date": window.current_date,
        "previous_items": [item.to_dict() for item in previous_items],
        "current_items": [item.to_dict() for item in current_items],
    }
    return (
        "请将以下新闻整理为前一日及当日要闻。必须按国内新闻、国际新闻两大板块，"
        "且每个板块包含 politics、economy_finance、society_welfare、industry、"
        "culture_sports 五个栏目。每条入选资讯都要给出 summary、impact、"
        "significance。只使用输入中的新闻，不要新增不存在的新闻。\n\n"
        "输出 JSON schema：\n"
        "{"
        '"executive_summary":"总览",'
        '"sections":{"domestic":{"categories":{"politics":{"items":[]},'
        '"economy_finance":{"items":[]},"society_welfare":{"items":[]},'
        '"industry":{"items":[]},"culture_sports":{"items":[]}}},'
        '"international":{"categories":{"politics":{"items":[]},'
        '"economy_finance":{"items":[]},"society_welfare":{"items":[]},'
        '"industry":{"items":[]},"culture_sports":{"items":[]}}}}'
        "}\n\n"
        f"新闻输入：{json.dumps(news_payload, ensure_ascii=False)}"
    )


def _guess_domain(item: NewsItem) -> str:
    text = f"{item.source} {item.title} {item.summary}".lower()
    international_markers = (
        "bbc",
        "world",
        "国际",
        "全球",
        "美国",
        "欧洲",
        "日本",
        "韩国",
        "俄罗斯",
        "乌克兰",
        "中东",
        "联合国",
    )
    return (
        "international"
        if any(marker.lower() in text for marker in international_markers)
        else "domestic"
    )


def _guess_category(item: NewsItem) -> str:
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
