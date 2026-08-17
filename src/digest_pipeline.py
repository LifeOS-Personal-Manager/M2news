"""
M2news Digest Pipeline — 全新的新闻聚合、评分与生成系统

工作流程:
  1. 读取 feeds.json + interests.json
  2. 并发抓取所有 RSS/JSON 源
  3. 时间窗硬过滤（丢弃未来时间、过期条目）
  4. MD5 去重（保留 weight 最高的源）
  5. 相关性 / 热度 / 新鲜度 三维打分
  6. 语义栏目分类
  7. 生成 HTML 页面（Top 5 + 分类折叠）

用法:
  python -m src.digest_pipeline
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import feedparser
import requests

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logger = logging.getLogger("digest_pipeline")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# ---------------------------------------------------------------------------
# 常量 / 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEEDS_PATH = PROJECT_ROOT / "feeds.json"
INTERESTS_PATH = PROJECT_ROOT / "interests.json"
OUTPUT_DIR = PROJECT_ROOT
DEFAULT_USER_AGENT = "M2newsDigest/1.0 (+mailto:your-email@example.com)"
REQUEST_TIMEOUT = 10
MAX_WORKERS = 10
MAX_ITEMS_PER_SOURCE = 50  # 每个源最多保留的条目数
AUTHORITATIVE_SOURCES = {
    "新华社最新",
    "新华网国际",
    "新华网金融",
    "新华网财经",
    "新华网科技",
    "人民网时政",
    "人民网社会",
    "人民网国际",
    "央视新闻",
    "央视国内",
    "央视国际",
    "央视财经",
    "央视社会",
    "中新社",
    "Reuters Asia",
    "AP Top News",
    "BBC World",
    "Guardian World",
    "Al Jazeera",
}


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_feeds() -> list[dict]:
    """加载 feeds.json 中的源列表。"""
    if not FEEDS_PATH.exists():
        raise FileNotFoundError(f"feeds.json not found at {FEEDS_PATH}")
    raw = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))
    sources = raw.get("sources", raw) if isinstance(raw, dict) else raw
    if not isinstance(sources, list):
        raise ValueError("feeds.json must contain a list of sources")
    enabled = [s for s in sources if s.get("enabled", True)]
    logger.info(
        "Loaded %d sources from feeds.json (%d enabled, %d disabled)",
        len(sources),
        len(enabled),
        len(sources) - len(enabled),
    )
    return enabled


def load_interests() -> dict:
    """加载 interests.json 中的兴趣权重与关键词。"""
    if not INTERESTS_PATH.exists():
        raise FileNotFoundError(f"interests.json not found at {INTERESTS_PATH}")
    data = json.loads(INTERESTS_PATH.read_text(encoding="utf-8"))
    weights = data["weights"]
    keywords = data["keywords"]
    logger.info("Loaded interests: %d topics", len(weights))
    return {"weights": weights, "keywords": keywords}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _strip_html(text: str) -> str:
    """清除 HTML 标签，保留纯文本。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_title(title: str) -> str:
    """规范化标题：去标点、转小写、去空格。"""
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", title).lower().strip()
    return s


def _title_md5(title: str) -> str:
    """基于规范化标题的 MD5 用于去重。"""
    return hashlib.md5(_normalize_title(title).encode("utf-8")).hexdigest()


def _parse_pubdate(entry: dict, fetch_time: datetime) -> datetime | None:
    """解析条目的 pubDate，返回 datetime 或 None。

    尝试多种策略:
      1. feedparser 已解析的 published_parsed / updated_parsed
      2. email.utils.parsedate_to_datetime 解析字符串
      3. 从 URL 中提取日期（如 /2022-12/09/ 或 /2022/12/09/）
    """
    raw = None
    for field in ("published", "pubDate", "updated", "updated_parsed"):
        val = entry.get(field)
        if val:
            raw = val
            break

    # 策略 1: feedparser 已解析
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed and hasattr(parsed, "tm_year") and parsed.tm_year > 2000:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    # 策略 2: 字符串解析
    if isinstance(raw, str):
        try:
            return parsedate_to_datetime(raw).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    # 策略 3: 从 URL 提取日期
    link = entry.get("link", "")
    date_match = re.search(r"/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/", link)
    if date_match:
        try:
            y, m, d = (
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
            )
            if 2000 <= y <= 2030:
                return datetime(y, m, d, tzinfo=timezone.utc)
        except (ValueError, OverflowError):
            pass

    return None


def _calc_similarity(t1: str, t2: str) -> float:
    """简单 Jaccard 相似度（基于字级别）。"""
    s1, s2 = set(t1), set(t2)
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


# ---------------------------------------------------------------------------
# 1. 数据抓取层
# ---------------------------------------------------------------------------
def fetch_source(source: dict) -> list[dict]:
    """抓取单个源，返回条目列表。"""
    name = source["name"]
    url = source["url"]
    parse_mode = source.get("parse_mode", "rss")
    weight = source.get("weight", 0.5)
    time_window_hours = source.get("time_window_hours", 24)
    source_type = source.get("type", "news")
    region = source.get("region", "domestic")

    fetch_time = datetime.now(timezone.utc)
    cutoff = fetch_time - timedelta(hours=time_window_hours)

    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": DEFAULT_USER_AGENT}
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Fetch failed for %s: %s", name, e)
        return []

    items: list[dict] = []

    if parse_mode in ("rss", "rsshub"):
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            title = _strip_html(entry.get("title", ""))
            link = entry.get("link", "")
            summary = _strip_html(
                entry.get("summary", "") or entry.get("description", "")
            )
            if not title:
                continue

            pubdate = _parse_pubdate(entry, fetch_time)

            # 时间窗硬过滤
            # 如果 pubDate 不存在 → 使用抓取时间（这种情况会被保留，因为它一定在窗口内）
            actual_pubdate = pubdate or fetch_time

            # 未来时间丢弃
            if actual_pubdate > fetch_time + timedelta(hours=1):
                logger.debug(
                    "Discard future-dated entry from %s: %s (%s)",
                    name,
                    title[:40],
                    actual_pubdate.isoformat(),
                )
                continue

            # 过期条目丢弃
            if actual_pubdate < cutoff:
                logger.debug(
                    "Discard expired entry from %s: %s (age %.1fh > window %dh)",
                    name,
                    title[:40],
                    (fetch_time - actual_pubdate).total_seconds() / 3600,
                    time_window_hours,
                )
                continue

            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source_name": name,
                    "source_weight": weight,
                    "source_type": source_type,
                    "region": region,
                    "pubdate": actual_pubdate,
                    "multiple_sources": 1,
                }
            )

        # 按发布时间降序排序，然后截断到 MAX_ITEMS_PER_SOURCE
        items.sort(key=lambda x: x["pubdate"], reverse=True)
        items = items[:MAX_ITEMS_PER_SOURCE]

    elif parse_mode == "json":
        try:
            data = (
                resp.json()
                if isinstance(resp.content, bytes)
                else json.loads(resp.content)
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("JSON parse failed for %s: %s", name, e)
            return []

        records = (
            data
            if isinstance(data, list)
            else data.get("items", data.get("articles", []))
        )
        for rec in records:
            title = _strip_html(rec.get("title", ""))
            link = rec.get("url") or rec.get("link", "")
            summary = _strip_html(rec.get("summary", "") or rec.get("description", ""))
            if not title:
                continue

            pubdate = _parse_pubdate(rec, fetch_time)
            actual_pubdate = pubdate or fetch_time

            if actual_pubdate > fetch_time + timedelta(hours=1):
                continue
            if actual_pubdate < cutoff:
                continue

            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source_name": name,
                    "source_weight": weight,
                    "source_type": source_type,
                    "region": region,
                    "pubdate": actual_pubdate,
                    "multiple_sources": 1,
                }
            )

    logger.info(
        "Fetched %d items from %s (window=%dh)", len(items), name, time_window_hours
    )
    return items


def fetch_all_sources(sources: list[dict]) -> list[dict]:
    """并发抓取所有源，返回扁平条目列表。"""
    all_items: list[dict] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        fut_map = {executor.submit(fetch_source, s): s["name"] for s in sources}
        for fut in as_completed(fut_map):
            name = fut_map[fut]
            try:
                items = fut.result()
                all_items.extend(items)
            except Exception as e:
                logger.error("Unhandled error fetching %s: %s", name, e)
    logger.info("Total raw items before dedup: %d", len(all_items))
    return all_items


# ---------------------------------------------------------------------------
# 2. 时间窗硬过滤（已在 fetch 中完成）
# 3. 去重
# ---------------------------------------------------------------------------
def deduplicate(items: list[dict]) -> list[dict]:
    """
    基于标题 MD5 去重。
    - 同一 MD5 只保留 weight 最高的源版本
    - 相似度 > 0.8 的合并，记录 multiple_sources
    """
    # 第一步：按 MD5 精确去重
    best_by_md5: dict[str, dict] = {}
    for item in items:
        md5 = _title_md5(item["title"])
        existing = best_by_md5.get(md5)
        if existing is None or item["source_weight"] > existing["source_weight"]:
            best_by_md5[md5] = item
        elif item["source_weight"] == existing["source_weight"]:
            # 相同 weight 时保留来源更多的
            existing["multiple_sources"] += 1

    # 第二步：模糊相似度合并
    deduped = list(best_by_md5.values())
    merged: list[dict] = []
    used = [False] * len(deduped)

    for i in range(len(deduped)):
        if used[i]:
            continue
        group = [deduped[i]]
        used[i] = True
        for j in range(i + 1, len(deduped)):
            if used[j]:
                continue
            if _calc_similarity(deduped[i]["title"], deduped[j]["title"]) > 0.8:
                group.append(deduped[j])
                used[j] = True

        # 取 group 中 weight 最高的作为代表
        best = max(group, key=lambda x: x["source_weight"])
        best["multiple_sources"] = sum(g.get("multiple_sources", 1) for g in group)
        merged.append(best)

    logger.info("After dedup: %d items (from %d raw)", len(merged), len(items))
    return merged


# ---------------------------------------------------------------------------
# 4. 相关性打分
# ---------------------------------------------------------------------------
def relevance_score(title: str, summary: str, interests: dict) -> float:
    """基于兴趣关键词计算相关性得分。"""
    text = f"{title} {summary}".lower()
    score = 0.0
    weights = interests["weights"]
    keywords = interests["keywords"]

    for topic, kws in keywords.items():
        hits = sum(1 for kw in kws if kw.lower() in text)
        if hits > 0:
            topic_weight = weights.get(topic, 0.1)
            score += topic_weight * min(hits / 3, 1.0)

    return score


# ---------------------------------------------------------------------------
# 5. 热度打分
# ---------------------------------------------------------------------------
def hotness_score(item: dict, source: dict) -> float:
    """基于来源类型、权威性、多源报道计算热度。"""
    score = 0.0
    # 热点榜来源加权
    if source.get("type") == "hotlist":
        score += 0.4
    # 权威通讯社加权
    if source.get("name") in AUTHORITATIVE_SOURCES:
        score += 0.3
    # 多源报道加权
    multi = item.get("multiple_sources", 1)
    if multi > 1:
        score += min(multi / 5, 0.3)
    return score


# ---------------------------------------------------------------------------
# 6. 新鲜度打分
# ---------------------------------------------------------------------------
def freshness_score(pubdate: datetime, now: datetime) -> float:
    """基于时间衰减计算新鲜度。"""
    age_hours = (now - pubdate).total_seconds() / 3600
    return max(0.0, 1.0 - age_hours / 24)


# ---------------------------------------------------------------------------
# 7. 综合排序
# ---------------------------------------------------------------------------
def compute_final_score(
    item: dict, source: dict, interests: dict, now: datetime
) -> dict:
    """计算条目综合得分并附加元数据。"""
    rel = relevance_score(item["title"], item["summary"], interests)
    hot = hotness_score(item, source)
    fresh = freshness_score(item["pubdate"], now)

    final = rel * 0.45 + hot * 0.35 + fresh * 0.20

    # 命中关键词
    text = f"{item['title']} {item['summary']}".lower()
    hit_keywords = set()
    interests_kw = interests["keywords"]
    for topic, kws in interests_kw.items():
        for kw in kws:
            if kw.lower() in text:
                hit_keywords.add(kw)
                break  # 每个 topic 只取一个

    item["relevance_score"] = round(rel, 4)
    item["hotness_score"] = round(hot, 4)
    item["freshness_score"] = round(fresh, 4)
    item["final_score"] = round(final, 4)
    item["confidence"] = round(final * 100, 1)  # 百分比
    item["hit_keywords"] = sorted(hit_keywords)[:5]
    return item


# ---------------------------------------------------------------------------
# 8. 语义栏目分类
# ---------------------------------------------------------------------------
def classify_category(title: str, summary: str) -> str:
    """基于关键词对条目进行语义分类。"""
    text = f"{title} {summary}".lower()
    categories = {
        "政治": [
            "主席",
            "总理",
            "政治局",
            "国务院",
            "人大",
            "政协",
            "政策",
            "宣言",
            "立法",
            "选举",
            "政府",
            "外交",
        ],
        "财经": [
            "股市",
            "汇率",
            "利率",
            "GDP",
            "CPI",
            "财报",
            "上市",
            "融资",
            "通胀",
            "降息",
            "加息",
            "原油",
            "黄金",
        ],
        "科技": [
            "AI",
            "芯片",
            "量子",
            "航天",
            "卫星",
            "机器人",
            "自动驾驶",
            "大模型",
            "GPT",
            "LLM",
            "人工智能",
        ],
        "国际": [
            "美国",
            "俄罗斯",
            "乌克兰",
            "欧盟",
            "日本",
            "韩国",
            "中东",
            "北约",
            "制裁",
            "联合国",
            "地缘",
        ],
        "社会": [
            "事故",
            "救援",
            "疫情",
            "教育",
            "医疗",
            "民生",
            "环保",
            "健康",
            "交通",
            "建设",
        ],
    }
    for cat, kws in categories.items():
        if any(kw in text for kw in kws):
            return cat
    return "其他"


# ---------------------------------------------------------------------------
# 9. 输出结构生成
# ---------------------------------------------------------------------------
def _format_relative_time(pubdate: datetime, now: datetime) -> str:
    """格式化相对时间，如 "2小时前"、"5分钟前"。"""
    delta = now - pubdate
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}秒前"
    elif seconds < 3600:
        return f"{seconds // 60}分钟前"
    elif seconds < 86400:
        return f"{seconds // 3600}小时前"
    else:
        return pubdate.strftime("%m-%d %H:%M")


def _get_source_badge_color(source_name: str) -> str:
    """根据来源名称返回徽章背景色。"""
    if source_name in ["微博热搜", "知乎热榜", "百度热点", "GitHub Trending"]:
        return "#00d8ff"  # 蓝青色 - 热点榜
    elif source_name in [
        "新华社最新",
        "新华网国际",
        "新华网金融",
        "新华网财经",
        "新华网科技",
        "新华网健康",
        "新华网体育",
        "人民网时政",
        "人民网社会",
        "人民网国际",
        "央视新闻",
        "央视国内",
        "央视国际",
        "央视财经",
        "央视社会",
        "央视文娱",
        "央视体育",
        "中新社",
    ]:
        return "#00ff88"  # 绿色 - 权威来源
    elif source_name in [
        "Reuters Asia",
        "AP Top News",
        "BBC World",
        "Guardian World",
        "Al Jazeera",
        "NPR News",
    ]:
        return "#ff5e62"  # 橙色 - 国际
    elif source_name in [
        "36氪最新",
        "MIT Tech Review",
        "BBC Technology",
        "Guardian Technology",
    ]:
        return "#a855f7"  # 紫色 - 科技
    elif source_name in [
        "财新最新",
        "WSJ Markets",
        "BBC Business",
        "Guardian Business",
    ]:
        return "#fbbf24"  # 黄色 - 财经
    else:
        return "#6b7280"  # 灰色 - 默认


def generate_html(
    all_items: list[dict],
    sources: list[dict],
    interests: dict,
    now: datetime,
) -> str:
    """生成完整的 HTML 字符串。深色科技风，响应式设计，Tab 切换。"""
    # 先计算所有得分
    source_map = {s["name"]: s for s in sources}
    scored: list[dict] = []
    for item in all_items:
        src = source_map.get(item["source_name"], {})
        scored.append(compute_final_score(item, src, interests, now))

    # 按综合分降序排序
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # Top 5
    top5 = scored[:5]

    # 剩余条目按栏目分类
    categories_order = ["政治", "财经", "科技", "国际", "社会", "其他"]
    by_category: dict[str, list[dict]] = {c: [] for c in categories_order}
    for item in scored[5:]:
        cat = classify_category(item["title"], item["summary"])
        if cat not in by_category:
            cat = "其他"
        by_category[cat].append(item)

    # 生成分类内的子排序（按综合分）
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x["final_score"], reverse=True)

    # 基础信息
    date_str = now.astimezone().strftime("%Y年%m月%d日")
    generated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    total_sources = len(sources)
    total_items = len(all_items)

    # 计算覆盖时间窗
    max_window_hours = (
        max(s.get("time_window_hours", 24) for s in sources) if sources else 24
    )

    # 构建 Top 5 的 HTML
    top5_html = ""
    for i, item in enumerate(top5, 1):
        kw_str = " ".join(item["hit_keywords"]) if item["hit_keywords"] else ""
        kw_tags = ""
        for kw in item["hit_keywords"][:3]:
            kw_tags += f'<span class="kw-tag">{_escape_html(kw)}</span>'

        relative_time = _format_relative_time(item["pubdate"], now)
        badge_color = _get_source_badge_color(item["source_name"])
        multi_source = item.get("multiple_sources", 1)

        score_pct = int(item["final_score"] * 100)
        top5_html += f"""
<div class="top-card">
  <div class="top-card-header">
    <span class="rank-badge rank-{i}">{i}</span>
    <span class="source-badge" style="background: {badge_color}">{_escape_html(item['source_name'])}</span>
    <span class="relative-time">{relative_time}</span>
  </div>
  <div class="top-card-body">
    <h3 class="top-title"><a href="{_escape_html(item['url'])}" target="_blank" rel="noopener">{_escape_html(item['title'])}</a></h3>
    <div class="score-bar-container">
      <div class="score-bar-label">综合分</div>
      <div class="score-bar">
        <div class="score-bar-fill" style="width: {score_pct}%"></div>
        <span class="score-bar-text">{score_pct}%</span>
      </div>
    </div>
    <div class="kw-section">
      <span class="kw-label">为什么重要</span>
      <div class="kw-tags">{kw_tags}</div>
    </div>
    <div class="top-summary">{_escape_html(item['summary'][:180])}</div>
  </div>
  {f'<div class="multi-source">📰 {multi_source} 个来源</div>' if multi_source > 1 else ''}
</div>"""

    # 构建分类 Tab 内容
    tab_nav_html = ""
    tab_content_html = ""
    for idx, cat in enumerate(categories_order):
        items = by_category.get(cat, [])
        active = "active" if idx == 0 else ""
        tab_nav_html += f'<button class="tab-btn {active}" data-tab="{cat}" onclick="switchTab(\'{cat}\')">{cat} <span class="tab-count">{len(items)}</span></button>'

        items_html = ""
        for item in items:
            relative_time = _format_relative_time(item["pubdate"], now)
            badge_color = _get_source_badge_color(item["source_name"])
            multi_source = item.get("multiple_sources", 1)
            kw_str = " ".join(
                [
                    f'<span class="kw-tag mini">{kw}</span>'
                    for kw in item["hit_keywords"][:2]
                ]
            )
            items_html += f"""
<article class="list-item">
  <a href="{_escape_html(item['url'])}" class="item-title" target="_blank" rel="noopener">{_escape_html(item['title'])}</a>
  <div class="item-meta">
    <span class="source-badge mini" style="background: {badge_color}">{_escape_html(item['source_name'])}</span>
    <span class="relative-time">{relative_time}</span>
    <span class="confidence">{item['confidence']:.0f}%</span>
    {f'<span class="multi-source mini">{multi_source} 源</span>' if multi_source > 1 else ''}
  </div>
  {f'<div class="item-kw"><span class="kw-label mini">为什么重要</span>{kw_str}</div>' if item["hit_keywords"] else ''}
</article>"""
        tab_content_html += f'<div class="tab-content {active}" data-tab-content="{cat}">{items_html}</div>'

    # 完整的 HTML 页面 - 深色科技风
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{date_str} 每日要闻</title>
  <style>
    :root {{
      --bg: #0a0b13;
      --bg-secondary: #141625;
      --bg-card: #1a1f35;
      --text-primary: #e2e8f0;
      --text-secondary: #94a3b8;
      --border: #2e344b;
      --accent: #00d4ff;
      --accent-secondary: #7c3aed;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --gradient: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%);
      --glow: 0 0 20px rgba(0, 212, 255, 0.3);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background: var(--bg);
      color: var(--text-primary);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      line-height: 1.6;
      min-height: 100vh;
    }}

    .container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 20px 16px 60px;
    }}

    /* Header */
    .top-header {{
      text-align: center;
      padding: 24px 0;
      border-bottom: 1px solid var(--border);
      margin-bottom: 24px;
    }}

    .top-header h1 {{
      font-size: 28px;
      font-weight: 700;
      background: var(--gradient);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 8px;
    }}

    .header-meta {{
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 16px;
      color: var(--text-secondary);
      font-size: 13px;
    }}

    /* Top 5 Section */
    .top-section {{
      margin-bottom: 32px;
    }}

    .top-section-title {{
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 16px;
      padding-left: 8px;
      border-left: 4px solid var(--accent);
      color: var(--text-primary);
    }}

    .top-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 12px;
      transition: all 0.2s;
    }}

    .top-card:hover {{
      border-color: var(--accent);
      box-shadow: var(--glow);
      transform: translateY(-2px);
    }}

    .top-card-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}

    .rank-badge {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      font-weight: 700;
      color: #000;
    }}

    .rank-1 {{ background: linear-gradient(135deg, #ffd700 0%, #ffb800 100%); }}
    .rank-2 {{ background: linear-gradient(135deg, #c0c0c0 0%, #a8a8a8 100%); }}
    .rank-3 {{ background: linear-gradient(135deg, #cd7f32 0%, #b87333 100%); }}
    .rank-4, .rank-5 {{ background: var(--accent); }}

    .source-badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 500;
      color: #000;
      opacity: 0.9;
    }}

    .source-badge.mini {{
      font-size: 10px;
      padding: 1px 6px;
    }}

    .relative-time {{
      color: var(--text-secondary);
      font-size: 12px;
      margin-left: auto;
    }}

    .top-title {{
      margin-bottom: 10px;
    }}

    .top-title a {{
      color: var(--text-primary);
      text-decoration: none;
      font-size: 18px;
      font-weight: 600;
      line-height: 1.4;
    }}

    .top-title a:hover {{
      color: var(--accent);
    }}

    .score-bar-container {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}

    .score-bar-label {{
      font-size: 12px;
      color: var(--text-secondary);
      width: 50px;
    }}

    .score-bar {{
      flex: 1;
      height: 12px;
      background: var(--border);
      border-radius: 6px;
      overflow: hidden;
      position: relative;
    }}

    .score-bar-fill {{
      height: 100%;
      background: var(--gradient);
      border-radius: 6px;
      transition: width 0.3s ease;
    }}

    .score-bar-text {{
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 10px;
      font-weight: 600;
      color: #000;
    }}

    .kw-tags {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}

    .kw-tag {{
      display: inline-block;
      padding: 2px 8px;
      background: var(--bg-secondary);
      border: 1px solid var(--border);
      border-radius: 4px;
      font-size: 11px;
      color: var(--accent);
    }}

    .kw-tag.mini {{
      font-size: 10px;
      padding: 1px 6px;
    }}

    .kw-section {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }}

    .kw-label {{
      font-size: 12px;
      color: var(--text-secondary);
      white-space: nowrap;
    }}

    .kw-label.mini {{
      font-size: 11px;
      color: var(--accent-secondary);
      font-weight: 500;
    }}

    .item-kw {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
      align-items: center;
    }}

    .top-summary {{
      font-size: 14px;
      color: var(--text-secondary);
      line-height: 1.6;
    }}

    .multi-source {{
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px dashed var(--border);
      font-size: 12px;
      color: var(--accent-secondary);
    }}

    .multi-source.mini {{
      margin: 0;
      padding: 0;
      border: none;
    }}

    /* Tab Section */
    .tab-container {{
      background: var(--bg-secondary);
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
    }}

    .tab-nav {{
      display: flex;
      overflow-x: auto;
      background: var(--bg-card);
      border-bottom: 1px solid var(--border);
      gap: 4px;
      padding: 8px;
    }}

    .tab-btn {{
      flex: 1;
      min-width: 70px;
      padding: 10px 8px;
      background: transparent;
      border: 1px solid transparent;
      border-radius: 6px;
      color: var(--text-secondary);
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s;
    }}

    .tab-btn:hover {{
      background: var(--bg-secondary);
      color: var(--text-primary);
    }}

    .tab-btn.active {{
      background: var(--gradient);
      color: #000;
      font-weight: 600;
    }}

    .tab-count {{
      display: inline-block;
      margin-left: 4px;
      padding: 1px 5px;
      background: rgba(0,0,0,0.2);
      border-radius: 10px;
      font-size: 11px;
      min-width: 18px;
      text-align: center;
    }}

    .tab-btn.active .tab-count {{
      background: rgba(255,255,255,0.2);
    }}

    .tab-content {{
      display: none;
      padding: 16px;
    }}

    .tab-content.active {{
      display: block;
    }}

    /* List Item */
    .list-item {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
      transition: all 0.2s;
    }}

    .list-item:last-child {{
      margin-bottom: 0;
    }}

    .list-item:hover {{
      border-color: var(--accent);
    }}

    .list-item .item-title {{
      display: block;
      color: var(--text-primary);
      text-decoration: none;
      font-size: 15px;
      font-weight: 500;
      margin-bottom: 8px;
      line-height: 1.5;
    }}

    .list-item .item-title:hover {{
      color: var(--accent);
    }}

    .list-item .item-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 6px;
    }}

    .list-item .confidence {{
      color: var(--text-secondary);
      font-size: 12px;
    }}

    .list-item .item-kw {{
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}

    /* Footer */
    .footer {{
      text-align: center;
      color: var(--text-secondary);
      font-size: 12px;
      margin-top: 32px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
    }}

    /* Responsive */
    @media (max-width: 640px) {{
      .container {{
        padding: 16px 12px 40px;
      }}
      .top-header h1 {{
        font-size: 22px;
      }}
      .top-title a {{
        font-size: 16px;
      }}
      .tab-nav {{
        padding: 6px 4px;
      }}
      .tab-btn {{
        min-width: 50px;
        padding: 8px 4px;
        font-size: 12px;
      }}
      .tab-content {{
        padding: 12px;
      }}
      .top-card {{
        padding: 12px;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="top-header">
      <h1>🔥 {date_str}</h1>
      <div class="header-meta">
        <span>⏱ 最后更新: {generated_at}</span>
        <span>🕐 覆盖时间窗: 最近 {max_window_hours} 小时</span>
        <span>📰 总计 {total_items} 条</span>
      </div>
    </header>

    <section class="top-section">
      <div class="top-section-title">今日 5 件大事</div>
      {top5_html}
    </section>

    <section class="tab-container">
      <div class="tab-nav">
        {tab_nav_html}
      </div>
      {tab_content_html}
    </section>

    <footer class="footer">
      M2news · 自动聚合评分 · 每 3 小时更新
    </footer>
  </div>

  <script>
    function switchTab(tabName) {{
      // 移除所有 active
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
      // 添加 active
      document.querySelector('.tab-btn[data-tab="' + tabName + '"]').classList.add('active');
      document.querySelector('.tab-content[data-tab-content="' + tabName + '"]').classList.add('active');
    }}
  </script>
</body>
</html>"""
    return html


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
# 10. 主流程
# ---------------------------------------------------------------------------
def run() -> None:
    """执行完整的数据采集 → 评分 → 生成流程。"""
    start = time.time()
    now = datetime.now(timezone.utc)

    logger.info("=" * 50)
    logger.info("M2news Digest Pipeline 开始运行")
    logger.info("=" * 50)

    # 1. 加载配置
    sources = load_feeds()
    interests = load_interests()

    # 2. 并发抓取
    logger.info("开始并发抓取 %d 个源...", len(sources))
    raw_items = fetch_all_sources(sources)
    logger.info("抓取完成，共 %d 条原始条目", len(raw_items))

    # 3. 去重
    deduped = deduplicate(raw_items)
    logger.info("去重后剩余 %d 条", len(deduped))

    # 4. 生成 HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = generate_html(deduped, sources, interests, now)

    html_path = OUTPUT_DIR / "latest.html"
    html_path.write_text(html, encoding="utf-8")
    logger.info("HTML 已生成: %s (%d 字节)", html_path, len(html))

    # 同时生成 JSON 输出
    json_path = OUTPUT_DIR / "latest.json"
    json_output = {
        "date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "total_sources": len(sources),
        "total_items": len(deduped),
        "items": [
            {
                "title": item["title"],
                "url": item["url"],
                "summary": item["summary"],
                "source": item["source_name"],
                "pubdate": item["pubdate"].isoformat(),
                "final_score": item["final_score"],
                "confidence": item["confidence"],
                "category": classify_category(item["title"], item["summary"]),
                "hit_keywords": item.get("hit_keywords", []),
            }
            for item in sorted(
                deduped, key=lambda x: x.get("final_score", 0), reverse=True
            )
        ],
    }
    json_path.write_text(
        json.dumps(json_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("JSON 已生成: %s", json_path)

    elapsed = time.time() - start
    logger.info("=" * 50)
    logger.info("流程完成！耗时 %.1f 秒", elapsed)
    logger.info("输出: %s, %s", html_path, json_path)
    logger.info("=" * 50)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        run()
    except Exception:
        logger.exception("FATAL: Pipeline crashed")
        raise


if __name__ == "__main__":
    main()
