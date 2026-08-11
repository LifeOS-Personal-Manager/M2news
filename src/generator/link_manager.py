from __future__ import annotations

import shutil
from pathlib import Path


class LinkManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def update_latest(self, date: str) -> tuple[Path, Path]:
        json_source = self.data_dir / f"{date}.json"
        html_source = self.data_dir / f"{date}.html"
        latest_json = self.data_dir / "latest.json"
        latest_html = self.data_dir / "latest.html"
        if not json_source.exists() or not html_source.exists():
            raise FileNotFoundError(f"Digest files for {date} do not exist")
        shutil.copyfile(json_source, latest_json)
        shutil.copyfile(html_source, latest_html)
        return latest_json, latest_html
