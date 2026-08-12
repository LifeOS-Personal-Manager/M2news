from __future__ import annotations

import json

from src.models import CATEGORIES, REGIONS, RawNewsItem

SYSTEM_PROMPT = """你是资深中文新闻值班主编。你的核心任务不是罗列新闻，而是筛选、判断、解读。

## 筛选标准（严格执行）
1. **重要性优先**：政策变动、经济数据、产业趋势、重大事件 > 日常动态
2. **影响范围**：影响数亿人 > 影响局部地区
3. **决策价值**：读者需要据此调整判断或行动的 > 可看可不看的
4. **信息密度**：有新事实、新数据、新进展 > 老调重弹
5. **排除项**：地方性过强、娱乐化、碎片化、标题党、无实质内容、纯公关稿

## 输出要求
- 每个板块（分类）最多保留 5 条，宁缺毋滥
- top_highlights 选全局最重要的 5 条，必须是真正有影响力的大事
- 同一事件多来源时合并为一条，保留多个 references
- 每条新闻必须包含：一句话事实、为什么重要、可能影响、来源链接
- 重要新闻 summary/impact 详细写，普通新闻简洁写
- 不得编造新闻、数据或结论
- 信息不足时写"信息不足，暂不解读"

输出必须是严格 JSON。"""

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
        f"以下是 {period_from} 至 {period_to} 期间的新闻素材。请以值班主编身份处理：\n\n"
        "## 第一步：筛选\n"
        "1. 通读全部 raw_items，识别真正重要的新闻\n"
        "2. 剔除：重复、低价值、地方性过强、娱乐化、碎片化、无实质信息的条目\n"
        "3. 每个分类（politics / economy_finance / society_welfare / industry / culture_sports）最多保留 5 条\n\n"
        "## 第二步：深度处理\n"
        "对保留的每条新闻：\n"
        "- summary：一句话讲清核心事实（30-80字）\n"
        "- impact：这件事的直接影响和长远影响（重要新闻写详细，可达150字）\n"
        "- why_it_matters：为什么读者需要关注（50-100字）\n"
        "- confidence：基于来源可靠性和信息完整度打 0-1 分\n\n"
        "## 第三步：重点速览\n"
        "top_highlights 选 5 条最重要的新闻标题，按影响力排序。\n\n"
        "## 第四步：排版\n"
        "- 国际和国内两大板块，每个板块下有 5 个分类\n"
        "- 无新闻的分类输出空列表即可\n"
        "- 不要平均分配篇幅，重要新闻多写，普通新闻少写\n\n"
        "必须输出与此结构兼容的严格 JSON：\n"
        f"{json.dumps(JSON_CONTRACT, ensure_ascii=False)}\n\n"
        "输入数据：\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
