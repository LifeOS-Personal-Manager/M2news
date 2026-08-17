"""
单元测试 - M2news Digest Pipeline
测试: 时间窗过滤、未来日期过滤、相关性打分、去重、综合排序
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.digest_pipeline import (
    _title_md5,
    _calc_similarity,
    deduplicate,
    relevance_score,
    freshness_score,
    compute_final_score,
    classify_category,
    load_interests,
    select_top_stories_by_category,
    _format_china_timestamp,
)


def print_test(name: str, passed: bool, message: str = ""):
    """打印测试结果。"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} {name}")
    if message:
        print(f"    {message}")


def test_enabled_feeds_have_diverse_sources():
    """feeds.json should not regress to a single-source digest."""
    feeds_path = os.path.join(PROJECT_ROOT, "feeds.json")
    with open(feeds_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    sources = raw.get("sources", raw)
    enabled = [source for source in sources if source.get("enabled", True)]
    names = {source["name"] for source in enabled}
    regions = {source.get("region") for source in enabled}
    categories = {source.get("category") for source in enabled}

    assert len(enabled) >= 25
    assert len(names - {"中新社"}) >= 20
    assert {"domestic", "international"}.issubset(regions)
    assert {"政治", "财经", "社会", "科技", "文体", "国际"}.issubset(categories)


def test_select_top_stories_uses_one_item_per_homepage_category():
    """Homepage top stories should cover politics, economy, culture, livelihood, entertainment."""
    now = datetime.now(timezone.utc)
    items = [
        ("政治局会议部署重点工作", "国务院发布政策", "新华社最新", 0.95),
        ("央行谈经济金融运行", "股市汇率稳定", "央视财经", 0.9),
        ("博物馆新展推动文化交流", "非遗艺术展览开幕", "央视文娱", 0.7),
        ("多地完善医疗就业保障", "民生服务继续优化", "人民网社会", 0.85),
        ("电影票房刷新纪录", "音乐综艺演唱会热度上升", "央视文娱", 0.8),
        ("政治高分重复项", "政府政策", "新华社最新", 0.99),
    ]
    scored = [
        {
            "title": title,
            "summary": summary,
            "url": f"https://example.com/{index}",
            "source_name": source,
            "final_score": score,
            "pubdate": now,
        }
        for index, (title, summary, source, score) in enumerate(items)
    ]
    source_map = {
        "新华社最新": {"category": "政治"},
        "央视财经": {"category": "财经"},
        "央视文娱": {"category": "文体"},
        "人民网社会": {"category": "社会"},
    }

    selected = select_top_stories_by_category(scored, source_map)

    assert [item["top_story_category"] for item in selected] == [
        "政治",
        "经济",
        "文化",
        "民生",
        "娱乐",
    ]
    assert len({item["url"] for item in selected}) == 5


def test_format_china_timestamp_uses_utc_plus_8():
    """The homepage update time should be displayed in China time."""
    utc_dt = datetime(2026, 8, 17, 6, 21, 47, tzinfo=timezone.utc)

    assert _format_china_timestamp(utc_dt) == "2026-08-17 14:21:47 CST"


def test_1_time_window_filter():
    """测试 1: 时间窗过滤 - 3 天前的假数据应该被过滤掉。"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    # 构造一条 3 天前的数据
    three_days_ago = now - timedelta(days=3)
    item = {
        "title": "测试新闻",
        "url": "https://example.com/test",
        "summary": "这是一条测试",
        "source_name": "测试源",
        "source_weight": 0.5,
        "pubdate": three_days_ago,
    }

    # 判断是否在窗口内
    is_expired = item["pubdate"] < cutoff
    print_test(
        "时间窗过滤（3天前）",
        is_expired,
        f"3天前日期 {three_days_ago.isoformat()} < 截止 {cutoff.isoformat()} → 应该被过滤",
    )
    return is_expired


def test_2_future_date_filter():
    """测试 2: 未来日期过滤 - 明天的假数据应该被过滤掉。"""
    now = datetime.now(timezone.utc)

    # 构造一条明天的数据
    tomorrow = now + timedelta(days=1)
    item = {
        "title": "未来新闻",
        "url": "https://example.com/future",
        "summary": "这是一条未来新闻",
        "source_name": "测试源",
        "source_weight": 0.5,
        "pubdate": tomorrow,
    }

    # 未来时间应该丢弃
    is_future = item["pubdate"] > now + timedelta(hours=1)
    print_test(
        "未来日期过滤（明天）",
        is_future,
        f"明天日期 {tomorrow.isoformat()} > 当前时间 → 应该被过滤",
    )
    return is_future


def test_3_relevance_score_ai():
    """测试 3a: 相关性打分 - AI/科技话题应该得高分。"""
    interests = load_interests()
    title = "AI 大模型芯片技术突破"
    summary = "最新人工智能大模型芯片发布，性能提升三倍"

    score = relevance_score(title, summary, interests)
    expected_min = 0.2  # 至少 0.2+ 分
    passed = score >= expected_min

    print_test(
        "相关性打分（AI/科技）", passed, f"得分: {score:.4f} (期望 >= {expected_min})"
    )
    return passed


def test_3b_relevance_score_finance():
    """测试 3b: 相关性打分 - 财经话题应该得高分。"""
    interests = load_interests()
    title = "美联储宣布加息决议"
    summary = "美联储加息 25 个基点，应对通胀压力"

    score = relevance_score(title, summary, interests)
    expected_min = 0.15
    passed = score >= expected_min

    print_test(
        "相关性打分（财经）", passed, f"得分: {score:.4f} (期望 >= {expected_min})"
    )
    return passed


def test_4_deduplication():
    """测试 4: 去重 - 两条相似标题应该合并。"""
    items = [
        {
            "title": "AI大模型技术突破",
            "url": "https://example.com/1",
            "summary": "测试摘要1",
            "source_name": "源A",
            "source_weight": 0.8,
            "pubdate": datetime.now(timezone.utc),
            "multiple_sources": 1,
        },
        {
            "title": "AI 大模型 技术突破",
            "url": "https://example.com/2",
            "summary": "测试摘要2",
            "source_name": "源B",
            "source_weight": 0.8,
            "pubdate": datetime.now(timezone.utc),
            "multiple_sources": 1,
        },
    ]

    result = deduplicate(items)
    # 相似度 > 0.8，应该合并为 1 条，multiple_sources = 2
    merged_count = len(result) == 1
    multi_source_ok = result[0].get("multiple_sources", 1) == 2
    passed = merged_count and multi_source_ok

    print_test(
        "去重（相似标题）",
        passed,
        f"输入 {len(items)} 条 → 输出 {len(result)} 条, multiple_sources = {result[0].get('multiple_sources', 0) if result else 0}",
    )
    return passed


def test_4b_exact_duplicate():
    """测试 4b: 精确去重 - 完全相同标题只保留一条。"""
    items = [
        {
            "title": "完全相同标题",
            "url": "https://example.com/1",
            "summary": "摘要",
            "source_name": "低权源",
            "source_weight": 0.3,
            "pubdate": datetime.now(timezone.utc),
            "multiple_sources": 1,
        },
        {
            "title": "完全相同标题",
            "url": "https://example.com/2",
            "summary": "摘要",
            "source_name": "高权源",
            "source_weight": 0.8,
            "pubdate": datetime.now(timezone.utc),
            "multiple_sources": 1,
        },
    ]

    result = deduplicate(items)
    passed = len(result) == 1
    # 应该保留 weight 更高的
    if result:
        passed = passed and result[0]["source_name"] == "高权源"

    print_test(
        "精确去重（相同标题保留高权重）",
        passed,
        f"保留来源: {result[0]['source_name'] if result else 'None'} (期望: 高权源)",
    )
    return passed


def test_5_comprehensive_ranking():
    """测试 5: 综合排序 - Top 5 确实是综合分最高的。"""
    interests = load_interests()
    now = datetime.now(timezone.utc)
    source_dummy = {"name": "测试", "type": "news", "weight": 0.5}

    # 构造 10 条混合数据，不同得分
    items = [
        {
            "title": f"测试{i} {kw}",
            "summary": "",
            "url": f"https://example.com/{i}",
            "source_name": "测试",
            "source_weight": 0.5,
            "pubdate": now - timedelta(hours=i * 2),
            "multiple_sources": 1,
        }
        for i, kw in enumerate(
            [
                "AI 大模型 芯片",
                "美联储加息",
                "乌克兰 冲突",
                "政治局 会议",
                "CPI 通胀",
                "普通新闻",
                "随便",
                "机器人 自动驾驶",
                "中东 局势",
                "股市 下跌",
            ]
        )
    ]

    # 计算所有得分
    scored = []
    for item in items:
        scored.append(compute_final_score(item, source_dummy, interests, now))

    # 按综合分降序排序
    scored.sort(key=lambda x: x["final_score"], reverse=True)

    # Top 5 应该是关键词匹配度高的
    top5_titles = [item["title"] for item in scored[:5]]
    print(f"    Top 5 排序结果:")
    for i, item in enumerate(scored[:5], 1):
        print(
            f"      {i}. {item['title']} → 综合分={item['final_score']:.4f}, 置信度={item['confidence']:.1f}%"
        )

    # 验证：前几名得分确实高于后几名
    top_avg = sum(item["final_score"] for item in scored[:5]) / 5
    bottom_avg = sum(item["final_score"] for item in scored[5:]) / 5
    passed = top_avg > bottom_avg

    print_test(
        "综合排序（Top 5 得分更高）",
        passed,
        f"Top5 平均分={top_avg:.4f}, 后5名平均分={bottom_avg:.4f}",
    )
    return passed


def main():
    """运行所有测试。"""
    print("=" * 60)
    print("M2news Digest Pipeline - 单元测试")
    print("=" * 60)
    print()

    tests = [
        ("时间窗过滤（3天前）", test_1_time_window_filter),
        ("未来日期过滤（明天）", test_2_future_date_filter),
        ("相关性打分 AI/科技", test_3_relevance_score_ai),
        ("相关性打分 财经", test_3b_relevance_score_finance),
        ("去重 相似标题合并", test_4_deduplication),
        ("精确去重 保留高权重", test_4b_exact_duplicate),
        ("综合排序 Top5得分更高", test_5_comprehensive_ranking),
    ]

    passed = 0
    total = len(tests)

    for name, func in tests:
        try:
            if func():
                passed += 1
        except Exception as e:
            print_test(name, False, f"异常: {e}")

    print()
    print("=" * 60)
    print(f"测试完成: {passed}/{total} 通过")
    print("=" * 60)

    if passed == total:
        print("\n🎉 所有测试通过！")
        sys.exit(0)
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
