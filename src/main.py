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

    collector = NewsCollector(settings)
    raw_items = collector.collect_all(target_date)
    analyzer = DigestAnalyzer(settings)
    digest = analyzer.analyze(
        target_date=target_date,
        period_from=period_from,
        period_to=period_to,
        items=raw_items,
    )
    file_store = FileStore(settings.output_dir)
    generator = DigestGenerator(file_store)
    json_path, html_path = generator.generate(digest)
    html_content = html_path.read_text(encoding="utf-8")
    SupabaseBackup(settings).backup(digest=digest, html_content=html_content)
    logger.info("Generated digest: %s and %s", json_path, html_path)
    return target_date


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run()


if __name__ == "__main__":
    main()
