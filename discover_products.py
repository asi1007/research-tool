from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_band import (
    DEFAULT_DISCOVERY_SHEET,
    DiscoveryBand,
    discovery_sheets,
)
from src.infrastructure.env import require_env
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.discover_products import (
    known_asins,
    plan_append,
    select_new_asins,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("discover_products")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keepaで発売半年以内・月販1000個以上の商品を探し自動調査タブへ積む（価格帯はタブ名から読む）"
    )
    parser.add_argument(
        "--sheet",
        help=f"対象タブ（既定: {DEFAULT_DISCOVERY_SHEET}）。価格帯はタブ名から読む",
    )
    parser.add_argument(
        "--all-sheets",
        action="store_true",
        help="価格帯を読めるすべての自動調査タブを安い順に処理する",
    )
    parser.add_argument("--limit", type=int, help="追記する件数の上限（タブごと）")
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

    try:
        bands = resolve_bands(args, repository)
    except ValueError as error:
        logger.error("対象タブを決められません", extra={"context": {"error": str(error)}})
        return 1

    known = collect_known(repository)
    exit_code = 0

    for band in bands:
        band_exit_code = discover_band(args, band, repository, keepa, known)
        exit_code = exit_code or band_exit_code

    return exit_code


def resolve_bands(
    args: argparse.Namespace, repository: GoogleSheetRepository
) -> list[DiscoveryBand]:
    if args.all_sheets:
        sheets = discovery_sheets(repository.sheet_titles())
        return [DiscoveryBand.from_sheet_name(sheet) for sheet in sheets]
    return [DiscoveryBand.from_sheet_name(args.sheet or DEFAULT_DISCOVERY_SHEET)]


def discover_band(
    args: argparse.Namespace,
    band: DiscoveryBand,
    repository: GoogleSheetRepository,
    keepa: KeepaClient,
    known: set[str],
) -> int:
    found = keepa.find_asins(band.criteria(), datetime.now(timezone.utc))
    fresh = select_new_asins(found, known, limit=args.limit)
    known.update(str(asin) for asin in fresh)

    logger.info(
        "発見しました",
        extra={
            "context": {
                "sheet": band.sheet,
                "min_price_yen": band.min_price_yen,
                "max_price_yen": band.max_price_yen,
                "found": len(found),
                "new": len(fresh),
            }
        },
    )
    for asin in fresh:
        print(f"{asin} {asin.amazon_url}")

    if args.dry_run:
        return 0

    if fresh:
        append_asins(band.sheet, fresh, repository)

    if args.no_fetch:
        return 0
    return subprocess.run(fetch_command(band.sheet), cwd=PROJECT_ROOT, check=False).returncode


def append_asins(
    sheet: str, asins: list[Asin], repository: GoogleSheetRepository
) -> None:
    values = repository.read_values(sheet)
    plan = plan_append(values, asins, date.today())
    if plan.rows_to_add:
        repository.ensure_rows(sheet, max(plan.updates))
    written = repository.apply_updates(sheet, plan.updates)

    logger.info(
        "自動調査タブへ追記しました",
        extra={"context": {"sheet": sheet, "cells": written, "rows": len(plan.updates)}},
    )


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
