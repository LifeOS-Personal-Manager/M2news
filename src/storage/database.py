from __future__ import annotations

import sqlite3
from pathlib import Path

from src.models import NewsItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    published_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_date ON news(date);
"""


class NewsDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_db(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert_items(self, items: list[NewsItem]) -> int:
        inserted = 0
        with self.connect() as connection:
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO news (
                        date, title, link, summary, source, hash,
                        published_at, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.date,
                        item.title,
                        item.link,
                        item.summary,
                        item.source,
                        item.hash,
                        item.published_at,
                        item.created_at,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def get_items_by_date(self, date: str) -> list[NewsItem]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT date, title, link, summary, source, hash,
                       published_at, created_at
                FROM news
                WHERE date = ?
                ORDER BY source, published_at DESC, created_at DESC
                """,
                (date,),
            ).fetchall()
        return [NewsItem.from_row(row) for row in rows]

    def get_latest_date(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT date FROM news GROUP BY date ORDER BY date DESC LIMIT 1"
            ).fetchone()
        return str(row["date"]) if row else None
