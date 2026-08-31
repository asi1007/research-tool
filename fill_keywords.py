from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_band import discovery_sheets
from src.infrastructure.ads_client import AdsApiError, AmazonAdsClient
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.fill_keywords import (
    ASIN_CODE,
    BID_CODE,
    HEADER_ROWS,
    KEYWORD_CODE,
    build_keyword_updates,
    parse_recommendations,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("fill_keywords")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ASINごとにAmazon Ads APIの推奨キーワードを引き、M列『検索ワード』とY列『広告単価』を埋める"
    )
    parser.add_argument("--sheet", help="対象タブ（省略時はすべての自動調査タブ）")
    parser.add_argument("--limit", type=int, help="処理する行数の上限")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず取得結果を表示する")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def build_ads_client() -> AmazonAdsClient:
    # 資格情報は広告プロジェクトと共有する（同じものを二重に持たない）
    load_dotenv(PROJECT_ROOT / require_env("AD_CREDENTIALS_ENV"))
    return AmazonAdsClient(
        client_id=os.environ["AMAZON_CLIENT_ID"],
        client_secret=os.environ["AMAZON_CLIENT_SECRET"],
        refresh_token=os.environ["AMAZON_REFRESH_TOKEN"],
        profile_id=os.environ["AMAZON_PROFILE_ID"],
        region=os.environ.get("AMAZON_REGION", "FE"),
    )


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def pending_asins(values: list[list]) -> list[Asin]:
    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    keyword_index = codes.index_of(KEYWORD_CODE)
    bid_index = codes.index_of(BID_CODE)
    if asin_index is None or keyword_index is None or bid_index is None:
        return []

    return [
        asin
        for row in values[HEADER_ROWS:]
        if (asin := Asin.parse(_cell(row, asin_index))) is not None
        and not _cell(row, keyword_index)
        and not _cell(row, bid_index)
    ]


def run(
    args: argparse.Namespace,
    repository: GoogleSheetRepository | None = None,
    client: AmazonAdsClient | None = None,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    repository = repository or build_repository()
    client = client or build_ads_client()

    sheets = [args.sheet] if args.sheet else discovery_sheets(repository.sheet_titles())
    total_written = 0

    for sheet in sheets:
        total_written += fill_sheet(args, sheet, repository, client)

    logger.info("完了しました", extra={"context": {"cells": total_written}})
    return 0


def fill_sheet(
    args: argparse.Namespace,
    sheet: str,
    repository: GoogleSheetRepository,
    client: AmazonAdsClient,
) -> int:
    values = repository.read_values(sheet)
    asins = pending_asins(values)
    if args.limit is not None:
        asins = asins[: args.limit]

    logger.info("対象を抽出しました", extra={"context": {"sheet": sheet, "count": len(asins)}})
    written = 0

    for asin in asins:
        suggestions = fetch_suggestions(client, sheet, asin)
        if not suggestions:
            continue

        if args.dry_run:
            print(f"{sheet}\t{asin}\t" + " / ".join(f"{s.keyword}:{s.bid_yen}" for s in suggestions))
            continue

        # 書き込む直前に読み直す。取得中に行が動いていても ASIN で引き直せる
        updates = build_keyword_updates(repository.read_values(sheet), str(asin), suggestions)
        written += repository.apply_updates(sheet, updates)

    logger.info("書き込みました", extra={"context": {"sheet": sheet, "cells": written}})
    return written


def fetch_suggestions(client: AmazonAdsClient, sheet: str, asin: Asin) -> list:
    try:
        return parse_recommendations(client.fetch_keyword_recommendations(asin))
    except AdsApiError as error:
        logger.warning(
            "推奨キーワードを取得できなかったためこの行はスキップします",
            extra={"context": {"sheet": sheet, "asin": str(asin), "error": str(error)}},
        )
        return []


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
