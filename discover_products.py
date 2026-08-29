from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
from src.infrastructure.env import require_env
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.discover_products import (
    DISCOVERY_SHEET,
    known_asins,
    plan_append,
    select_new_asins,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("discover_products")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keepaで発売半年以内・月販1000個以上・1000円以下の商品を探し自動調査タブへ積む"
    )
    parser.add_argument("--limit", type=int, help="追記する件数の上限")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず件数だけ表示する")
    parser.add_argument("--no-fetch", action="store_true", help="商品情報の取得を続けて行わない")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def build_keepa() -> KeepaClient:
    return KeepaClient(require_env("KEEPA_API_KEY"))


def fetch_command(sheet: str) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "fetch_products.py"),
        "--sheet",
        sheet,
        "--interval",
        "auto",
    ]


def collect_known(repository: GoogleSheetRepository) -> set[str]:
    return known_asins(repository.read_all_values())


def run(
    args: argparse.Namespace,
    repository: GoogleSheetRepository | None = None,
    keepa: KeepaClient | None = None,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    keepa = keepa or build_keepa()
    repository = repository or build_repository()

    found = keepa.find_asins(DiscoveryCriteria(), datetime.now(timezone.utc))
    fresh = select_new_asins(found, collect_known(repository), limit=args.limit)

    logger.info(
        "発見しました",
        extra={"context": {"found": len(found), "new": len(fresh)}},
    )
    for asin in fresh:
        print(f"{asin} {asin.amazon_url}")

    if args.dry_run:
        return 0

    if fresh:
        values = repository.read_values(DISCOVERY_SHEET)
        plan = plan_append(values, fresh, date.today())
        if plan.rows_to_add:
            repository.ensure_rows(DISCOVERY_SHEET, max(plan.updates))
        written = repository.apply_updates(DISCOVERY_SHEET, plan.updates)

        logger.info(
            "自動調査タブへ追記しました",
            extra={"context": {"cells": written, "rows": len(plan.updates)}},
        )

    if args.no_fetch:
        return 0
    return subprocess.run(fetch_command(DISCOVERY_SHEET), cwd=PROJECT_ROOT, check=False).returncode


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
