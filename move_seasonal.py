from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_band import discovery_sheets
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.drop_marked import build_transfer_rows
from src.usecases.seasonal import (
    ASIN_CODE,
    SEASONAL_SHEET,
    TITLE_CODE,
    seasonal_row_numbers,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("move_seasonal")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"夏物・冬物の行を「{SEASONAL_SHEET}」タブへ移し、元タブから削除する"
    )
    parser.add_argument("--sheet", help="対象タブ（省略時はすべての自動調査タブ）")
    parser.add_argument("--dry-run", action="store_true", help="移さず対象だけ表示する")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def resolve_sheets(args: argparse.Namespace, repository: GoogleSheetRepository) -> list[str]:
    if args.sheet:
        return [args.sheet]
    return discovery_sheets(repository.sheet_titles())


def run(args: argparse.Namespace, repository: GoogleSheetRepository | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    repository = repository or build_repository()

    seasonal_values = repository.read_values(SEASONAL_SHEET)
    total = 0

    for sheet in resolve_sheets(args, repository):
        total += move_sheet(args, sheet, seasonal_values, repository)

    logger.info("完了しました", extra={"context": {"moved": total}})
    return 0


def move_sheet(
    args: argparse.Namespace,
    sheet: str,
    seasonal_values: list[list],
    repository: GoogleSheetRepository,
) -> int:
    values = repository.read_values(sheet)
    row_numbers = seasonal_row_numbers(values)
    if not row_numbers:
        return 0

    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    title_index = codes.index_of(TITLE_CODE)
    for row_number in row_numbers:
        row = values[row_number - 1]
        asin = str(row[asin_index]) if asin_index is not None and asin_index < len(row) else ""
        title = str(row[title_index])[:34] if title_index is not None and title_index < len(row) else ""
        print(f"{sheet}\t{row_number}\t{asin}\t{title}")

    if args.dry_run:
        return len(row_numbers)

    repository.append_rows(SEASONAL_SHEET, build_transfer_rows(values, seasonal_values, row_numbers))
    repository.delete_rows(sheet, row_numbers)

    logger.info(
        f"{SEASONAL_SHEET}へ移しました",
        extra={"context": {"sheet": sheet, "rows": len(row_numbers)}},
    )
    return len(row_numbers)


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
