"""
M2news — 主入口

用法:
  python -m src.main

直接调用新版的 digest_pipeline 完成采集 → 评分 → 生成。
"""
from __future__ import annotations

import logging

from src.digest_pipeline import run as pipeline_run, main as pipeline_main

logger = logging.getLogger(__name__)


def run() -> str:
    """执行新版管道，返回目标日期字符串。"""
    pipeline_run()
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    try:
        run()
    except Exception:
        logger.exception("FATAL ERROR: Pipeline crashed")
        raise


if __name__ == "__main__":
    main()