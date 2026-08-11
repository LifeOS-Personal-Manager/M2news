from __future__ import annotations

import logging
from typing import Any

import requests

from src.config import Settings
from src.models import CATEGORIES, REGIONS, DailyDigest

logger = logging.getLogger(__name__)


class SupabaseBackup:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.enable_supabase_backup
            and self.settings.supabase_url
            and self.settings.supabase_service_role_key
        )

    def backup(self, *, digest: DailyDigest, html_content: str) -> None:
        if not self.enabled:
            logger.info("Supabase backup skipped: not configured")
            return
        payload = digest.to_dict()
        self._upsert_digest(payload, html_content)
        self._upsert_articles(payload)

    def _headers(self) -> dict[str, str]:
        key = self.settings.supabase_service_role_key or ""
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }

    def _upsert_digest(self, payload: dict[str, Any], html_content: str) -> None:
        row = {
            "digest_date": payload["date"],
            "period_from": payload["period"]["from"],
            "period_to": payload["period"]["to"],
            "json_payload": payload,
            "html_content": html_content,
            "generated_at": payload["generated_at"],
        }
        self._post(
            table=self.settings.supabase_table_digests,
            rows=[row],
            on_conflict="digest_date",
        )

    def _upsert_articles(self, payload: dict[str, Any]) -> None:
        rows = []
        for region in REGIONS:
            for category in CATEGORIES:
                for article in payload["sections"][region][category]:
                    rows.append(
                        {
                            "digest_date": payload["date"],
                            "hash": article["hash"],
                            "title": article["title"],
                            "source": article["source"],
                            "url": article["url"],
                            "region": article["region"],
                            "category": article["category"],
                            "published_at": article["published_at"],
                            "summary": article["summary"],
                            "impact": article["impact"],
                            "why_it_matters": article["why_it_matters"],
                            "confidence": article["confidence"],
                            "raw_payload": article,
                        }
                    )
        if rows:
            self._post(
                table=self.settings.supabase_table_articles,
                rows=rows,
                on_conflict="digest_date,hash",
            )

    def _post(
        self,
        *,
        table: str,
        rows: list[dict[str, Any]],
        on_conflict: str,
    ) -> None:
        url = (
            f"{self.settings.supabase_url.rstrip('/')}/rest/v1/{table}"
            f"?on_conflict={on_conflict}"
        )
        response = requests.post(
            url,
            headers=self._headers(),
            json=rows,
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
