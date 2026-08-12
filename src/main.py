from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.collector.collector import NewsCollector
from src.config import Settings, load_settings
from src.generator.digest_generator import DigestGenerator
from src.llm.digest_analyzer import DigestAnalyzer
from src.storage.file_store import FileStore
from src.storage.supabase_backup import SupabaseBackup

logger = logging.getLogger(__name__)


def run(settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    target_date = today.isoformat()
    period_from = (today - timedelta(days=1)).isoformat()
    period_to = target_date

    logger.info("=== M2news Digest Run ===")
    logger.info("Target date: %s (period: %s ~ %s)", target_date, period_from, period_to)
    logger.info("News sources: %d configured", len(settings.news_sources))
    for src in settings.news_sources:
        logger.info("  - %s [%s] (%s) enabled=%s", src.name, src.region, src.type, src.enabled)
    logger.info("LLM enabled=%s model=%s api_key=%s",
                settings.enable_llm_analysis, settings.openai_model,
                "SET" if settings.openai_api_key else "NOT SET")
    logger.info("Output dir: %s", settings.output_dir)

    collector = NewsCollector(settings)
    raw_items = collector.collect_all(target_date)
    logger.info("Collected %d raw items from all sources", len(raw_items))

    analyzer = DigestAnalyzer(settings)
    digest = analyzer.analyze(
        target_date=target_date,
        period_from=period_from,
        period_to=period_to,
        items=raw_items,
    )
    total_articles = sum(
        len(digest.sections[r][c])
        for r in digest.sections
        for c in digest.sections[r]
    )
    logger.info("Digest analyzed: %d articles, %d highlights", total_articles, len(digest.top_highlights))

    file_store = FileStore(settings.output_dir)
    generator = DigestGenerator(file_store)
    json_path, html_path = generator.generate(digest)
    logger.info("Generated: %s, %s", json_path, html_path)

    html_content = html_path.read_text(encoding="utf-8")
    try:
        SupabaseBackup(settings).backup(digest=digest, html_content=html_content)
    except Exception:
        logger.exception("Supabase backup failed (non-fatal)")

    logger.info("=== Digest completed successfully ===")
    return target_date


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        run()
    except Exception:
        logger.exception("FATAL ERROR: Pipeline crashed")
        raise


if __name__ == "__main__":
    main()
