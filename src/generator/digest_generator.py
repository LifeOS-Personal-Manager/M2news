from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import CATEGORIES, REGIONS, DailyDigest
from src.storage.file_store import FileStore

REGION_LABELS = {
    "international": "国际新闻",
    "domestic": "国内新闻",
}

CATEGORY_LABELS = {
    "politics": "政治发展",
    "economy_finance": "经济金融",
    "society_welfare": "社会民生保障",
    "industry": "产业行业",
    "culture_sports": "文化体育",
}


class DigestGenerator:
    def __init__(self, file_store: FileStore) -> None:
        self.file_store = file_store
        template_dir = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, digest: DailyDigest) -> tuple[Path, Path]:
        json_path = self.file_store.write_digest_json(digest)
        html_path = self.file_store.write_digest_html(
            digest.date,
            self.render_html(digest),
        )
        self.file_store.update_latest(digest.date)
        return json_path, html_path

    def render_html(self, digest: DailyDigest) -> str:
        template = self.env.get_template("digest.html.j2")
        return template.render(
            digest=digest.to_dict(),
            regions=REGIONS,
            categories=CATEGORIES,
            region_labels=REGION_LABELS,
            category_labels=CATEGORY_LABELS,
            page_title=_page_title(digest.date),
        )


def _page_title(date: str) -> str:
    try:
        year, month, day = date.split("-")
        return f"{year}年{int(month)}月{int(day)}日 前日及当日要闻解读"
    except ValueError:
        return f"{date} 前日及当日要闻解读"
