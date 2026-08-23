from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.exchange_rate_client import fetch_cny_to_jpy_rate
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.infrastructure.shipping_calculator import (
    DEFAULT_RATE_PER_KG_CNY,
    InternationalShippingCalculator,
)
from src.infrastructure.spapi_client import SpApiClient
from src.usecases.bulk_fetch_products import BulkFetchProductsUseCase, SheetResult
from src.usecases.product_info_fetcher import ProductInfoFetcher

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_AUTO_INTERVAL_SECONDS = 12.0
DEFAULT_SHEETS = (
    "優先",
    "候補",
    "リサーチ700円以下",
    "1000円周辺",
    "単価1500~",
    "単価2000~",
    "ハードル高い",
    "季節商品",
    "候補外",
)

logger = logging.getLogger("fetch_products")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="C列のASIN/商品URLからKeepa・SP-APIで商品情報を取得しシートへ書き込む"
    )
    parser.add_argument("--sheet", action="append", dest="sheets", help="対象シート名（複数指定可）")
    parser.add_argument("--all", action="store_true", help=f"既定の{len(DEFAULT_SHEETS)}シートを対象にする")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず件数だけ表示する")
    parser.add_argument("--overwrite", action="store_true", help="既存の値も上書きする")
    parser.add_argument("--limit", type=int, help="シートごとの取得件数上限")
    parser.add_argument(
        "--interval",
        default="1.0",
        help="API呼び出しの間隔秒数。auto でKeepaの補充レートに合わせる（他の処理を圧迫しない）",
    )
    parser.add_argument("--rate-per-kg", type=float, default=DEFAULT_RATE_PER_KG_CNY,
                        help="国際送料の単価（元/kg）")
    parser.add_argument("--checkpoint", type=int, default=25,
                        help="この件数ごとにシートへ途中保存する（0で無効）")
    parser.add_argument("--count-only", action="store_true",
                        help="APIを呼ばず、取得が必要な行数だけを数える")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def resolve_sheets(args: argparse.Namespace) -> list[str]:
    if args.sheets:
        return args.sheets
    if args.all:
        return list(DEFAULT_SHEETS)
    return []


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"環境変数 {name} が設定されていません。.env を確認してください。")
    return value


def resolve_interval(raw: str, keepa: KeepaClient) -> float:
    if str(raw).lower() != "auto":
        return float(raw)

    refill_rate = keepa.fetch_refill_rate_per_minute()
    if not refill_rate:
        logger.warning(
            "補充レートを取得できなかったため既定間隔を使用",
            extra={"context": {"interval_seconds": DEFAULT_AUTO_INTERVAL_SECONDS}},
        )
        return DEFAULT_AUTO_INTERVAL_SECONDS

    interval = 60.0 / refill_rate
    logger.info(
        "Keepaの補充レートに合わせて間隔を設定",
        extra={
            "context": {
                "refill_rate_per_minute": refill_rate,
                "interval_seconds": interval,
                "tokens_left": keepa.tokens_left,
            }
        },
    )
    return interval


def build_usecase(args: argparse.Namespace) -> BulkFetchProductsUseCase:
    repository = GoogleSheetRepository(
        service_account_file=str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        spreadsheet_id=require_env("RESEARCH_SPREADSHEET_ID"),
    )
    keepa = KeepaClient(require_env("KEEPA_API_KEY"))
    fetcher = ProductInfoFetcher(
        keepa=keepa,
        spapi=SpApiClient(
            refresh_token=require_env("SP_API_REFRESH_TOKEN"),
            client_id=require_env("SP_API_CLIENT_ID"),
            client_secret=require_env("SP_API_CLIENT_SECRET"),
        ),
    )
    calculator = InternationalShippingCalculator(
        rate_per_kg_cny=args.rate_per_kg, cny_to_jpy_rate=fetch_cny_to_jpy_rate()
    )

    return BulkFetchProductsUseCase(
        repository=repository,
        fetcher=fetcher,
        shipping_calculator=calculator,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        interval_seconds=resolve_interval(args.interval, keepa),
        checkpoint_size=args.checkpoint,
    )


def print_summary(results: list[SheetResult], dry_run: bool) -> None:
    label = "書き込み予定" if dry_run else "書き込み"

    print(f"\n{'シート':<20}{'行数':>6}{'取得':>6}{'既存':>6}{'無効':>6}{'失敗':>6}{label:>12}")
    print("-" * 68)
    for result in results:
        print(
            f"{result.sheet_name:<20}{result.total_rows:>6}{result.fetched:>6}"
            f"{result.already_filled:>6}{result.invalid_asin:>6}{len(result.failed):>6}"
            f"{result.updated_cells:>12}"
        )
    print("-" * 68)
    print(
        f"{'合計':<20}{sum(r.total_rows for r in results):>6}"
        f"{sum(r.fetched for r in results):>6}{sum(r.already_filled for r in results):>6}"
        f"{sum(r.invalid_asin for r in results):>6}{sum(len(r.failed) for r in results):>6}"
        f"{sum(r.updated_cells for r in results):>12}"
    )


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    load_dotenv(PROJECT_ROOT / ".env")

    sheets = resolve_sheets(args)
    if not sheets:
        print("対象シートを --sheet で指定するか --all を付けてください。", file=sys.stderr)
        print(f"既定の対象: {', '.join(DEFAULT_SHEETS)}", file=sys.stderr)
        return 1

    usecase = build_usecase(args)

    results = []
    for sheet_name in sheets:
        logger.info("シートの処理を開始", extra={"context": {"sheet": sheet_name}})
        try:
            if args.count_only:
                results.append(usecase.count_targets(sheet_name))
            else:
                results.append(usecase.execute(sheet_name, limit=args.limit))
        except Exception as error:
            logger.error(
                "シートの処理に失敗", extra={"context": {"sheet": sheet_name}}, exc_info=error
            )

    print_summary(results, dry_run=args.dry_run or args.count_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
