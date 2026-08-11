from __future__ import annotations

from pathlib import Path


class Uploader:
    """Extension point for future static hosting or object storage upload."""

    def upload(self, paths: list[Path]) -> list[str]:
        return [str(path) for path in paths]
