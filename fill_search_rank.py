from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_band import discovery_sheets
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.infrastructure.spapi_reports_client import SpApiReportsClient
from src.usecases.search_rank import build_rank_index, build_rank_updates, last_sunday

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "data"
REPORT_DAYS = 7

logger = logging.getLogger("fill_search_rank")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Brand Analyticsの検索キーワードレポートから、M列の検索ワードの検索順位をBT列へ入れる"
    )
    parser.add_argument("--sheet", help="対象タブ（省略時はすべての自動調査タブ）")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず対象件数を表示する")
    parser.add_argument("--refresh", action="store_true", help="キャッシュを使わずレポートを取り直す")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def build_client() -> SpApiReportsClient:
    return SpApiReportsClient(
        client_id=require_env("SP_API_CLIENT_ID"),
        client_secret=require_env("SP_API_CLIENT_SECRET"),
        refresh_token=require_env("SP_API_REFRESH_TOKEN"),
    )


def load_rank_index(args: argparse.Namespace, client: SpApiReportsClient, today: date) -> dict[str, int]:
    start = last_sunday(today)
    cache_path = CACHE_DIR / f"search_rank_{start.isoformat()}.json"

    if cache_path.exists() and not args.refresh:
        logger.info("キャッシュを使います", extra={"context": {"path": str(cache_path)}})
        return {term: int(rank) for term, rank in json.loads(cache_path.read_text()).items()}

    # レポートは130万語・数十MBある。週次更新なので同じ週なら取り直さない
    report = client.fetch_search_terms_report(start, start + timedelta(days=REPORT_DAYS - 1))
    index = build_rank_index(report)

    CACHE_DIR.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps(index, ensure_ascii=False))
    logger.info(
        "レポートを取得しました",
        extra={"context": {"start": start.isoformat(), "keywords": len(index)}},
    )
    return index


def run(
    args: argparse.Namespace,
    repository: GoogleSheetRepository | None = None,
    client: SpApiReportsClient | None = None,
    today: date | None = None,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    repository = repository or build_repository()
    client = client or build_client()

    index = load_rank_index(args, client, today or date.today())
    sheets = [args.sheet] if args.sheet else discovery_sheets(repository.sheet_titles())
    total = 0

    for sheet in sheets:
        updates = build_rank_updates(repository.read_values(sheet), index)
        logger.info("対象を抽出しました", extra={"context": {"sheet": sheet, "rows": len(updates)}})

        if args.dry_run:
            continue
        total += repository.apply_updates(sheet, updates)

    logger.info("完了しました", extra={"context": {"cells": total}})
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
