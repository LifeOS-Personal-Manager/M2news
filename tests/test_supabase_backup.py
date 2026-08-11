from __future__ import annotations

from src.models import DailyDigest, empty_sections, utc_now_iso
from src.storage.supabase_backup import SupabaseBackup
from tests.test_collector import make_settings


def test_supabase_backup_skips_when_not_configured(tmp_path):
    settings = make_settings(tmp_path, [])
    digest = DailyDigest(
        date="2026-08-11",
        period={"from": "2026-08-10", "to": "2026-08-11"},
        sections=empty_sections(),
        top_highlights=[],
        generated_at=utc_now_iso(),
    )

    SupabaseBackup(settings).backup(digest=digest, html_content="<html></html>")
