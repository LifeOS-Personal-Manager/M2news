from __future__ import annotations

import argparse
import logging
import time

from src.config import load_settings
from src.scheduler.scheduler import DigestJob, build_scheduler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal news digest scheduler")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the digest job once and exit",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    args = parse_args()
    if args.run_once:
        DigestJob(settings).run_once()
        return

    scheduler = build_scheduler(settings)
    scheduler.start()
    logging.getLogger(__name__).info("Scheduler started")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
