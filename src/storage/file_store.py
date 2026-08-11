from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from src.models import DailyDigest


class FileStore:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def json_path(self, date: str) -> Path:
        return self.output_dir / f"{date}.json"

    def html_path(self, date: str) -> Path:
        return self.output_dir / f"{date}.html"

    def write_digest_json(self, digest: DailyDigest) -> Path:
        path = self.json_path(digest.date)
        write_json(path, digest.to_dict())
        return path

    def write_digest_html(self, date: str, html: str) -> Path:
        path = self.html_path(date)
        atomic_write_text(path, html)
        return path

    def update_latest(self, date: str) -> tuple[Path, Path]:
        json_source = self.json_path(date)
        html_source = self.html_path(date)
        latest_json = self.output_dir / "latest.json"
        latest_html = self.output_dir / "latest.html"
        if not json_source.exists() or not html_source.exists():
            raise FileNotFoundError(f"Digest files for {date} do not exist")
        shutil.copyfile(json_source, latest_json)
        shutil.copyfile(html_source, latest_html)
        return latest_json, latest_html

    def write_json(
        self,
        date: str,
        items: list[Any],
        analysis: dict[str, Any] | None = None,
    ) -> Path:
        payload = {
            "date": date,
            "count": len(items),
            "items": [
                item.to_dict() if hasattr(item, "to_dict") else item for item in items
            ],
        }
        if analysis is not None:
            payload["analysis"] = analysis
        path = self.json_path(date)
        write_json(path, payload)
        return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)
