from __future__ import annotations

import json

from src.models import DailyDigest, empty_sections, make_url_hash, utc_now_iso
from src.storage.file_store import FileStore


def test_file_store_writes_latest_files(tmp_path):
    digest = DailyDigest(
        date="2026-08-11",
        period={"from": "2026-08-10", "to": "2026-08-11"},
        sections=empty_sections(),
        top_highlights=[],
        generated_at=utc_now_iso(),
    )
    store = FileStore(tmp_path)

    store.write_digest_json(digest)
    (tmp_path / "2026-08-11.html").write_text("<h1>ok</h1>", encoding="utf-8")
    latest_json, latest_html = store.update_latest("2026-08-11")

    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    assert payload["date"] == "2026-08-11"
    assert latest_html.read_text(encoding="utf-8") == "<h1>ok</h1>"


def test_make_url_hash_removes_tracking_query():
    assert make_url_hash("https://example.com/a?utm_campaign=x") == make_url_hash(
        "https://example.com/a"
    )
