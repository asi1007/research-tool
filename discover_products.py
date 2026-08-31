from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
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
    select_by_revenue,
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
    parser.add_argument(
        "--no-keywords",
        action="store_true",
        help="M列『検索ワード』とY列『広告単価』の書き込みを行わない",
    )
    parser.add_argument(
        "--no-shorten",
        action="store_true",
        help="H列『商品名(BUY)』への短縮名の書き込みを行わない",
    )
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


def shorten_command(sheet: str) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "shorten_titles.py"),
        "--sheet",
        sheet,
    ]


def keyword_command(sheet: str) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "fill_keywords.py"),
        "--sheet",
        sheet,
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
    criteria = band.criteria()
    found = keepa.find_asins(criteria, datetime.now(timezone.utc))
    # 実測は既知ASINを除いてから行う。Keepa のトークンは1件1消費なので無駄打ちを避ける
    unknown = select_new_asins(found, known)
    fresh = [] if args.dry_run else select_new_by_revenue(args, unknown, criteria, keepa)
    known.update(str(asin) for asin in fresh)

    logger.info(
        "発見しました",
        extra={
            "context": {
                "sheet": band.sheet,
                "min_price_yen": band.min_price_yen,
                "max_price_yen": band.max_price_yen,
                "found": len(found),
                "unknown": len(unknown),
                "new": len(fresh),
            }
        },
    )
    for asin in fresh or unknown:
        print(f"{asin} {asin.amazon_url}")

    if args.dry_run:
        return 0

    if fresh:
        append_asins(band.sheet, fresh, repository)

    if args.no_fetch:
        return 0
    return complete_rows(args, band.sheet)


def complete_rows(args: argparse.Namespace, sheet: str) -> int:
    # 商品情報の取得が一部失敗しても、取れた行の短縮名は書けるので続行する
    exit_code = subprocess.run(fetch_command(sheet), cwd=PROJECT_ROOT, check=False).returncode

    for skipped, command in (
        (args.no_shorten, shorten_command(sheet)),
        (args.no_keywords, keyword_command(sheet)),
    ):
        if skipped:
            continue
        step_exit_code = subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode
        exit_code = exit_code or step_exit_code

    return exit_code


def select_new_by_revenue(
    args: argparse.Namespace,
    unknown: list[Asin],
    criteria: DiscoveryCriteria,
    keepa: KeepaClient,
) -> list[Asin]:
    profitable = select_by_revenue(keepa.fetch_products(unknown), criteria)
    return profitable[: args.limit] if args.limit is not None else profitable


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
