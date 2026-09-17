from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_band import discovery_sheets
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.drop_marked import (
    ASIN_CODE,
    MARK_DESTINATIONS,
    plan_transfer,
    marked_row_numbers,
)
from src.infrastructure.column_codes import ColumnCodes

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("drop_marked")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A列の印（d=候補外、s=季節商品、p=保留）ごとに行を移し、元タブから削除する"
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

    total_moved = 0

    for sheet in resolve_sheets(args, repository):
        # 印ごとに読み直す。前の印の行を消すと行番号がずれる
        for mark, destination in MARK_DESTINATIONS.items():
            total_moved += drop_sheet(args, sheet, mark, destination, repository)

    logger.info("完了しました", extra={"context": {"moved": total_moved}})
    return 0


def drop_sheet(
    args: argparse.Namespace,
    sheet: str,
    mark: str,
    destination: str,
    repository: GoogleSheetRepository,
) -> int:
    values = repository.read_values(sheet)
    row_numbers = marked_row_numbers(values, mark)
    if not row_numbers:
        return 0

    asin_index = ColumnCodes(values).index_of(ASIN_CODE)
    for row_number in row_numbers:
        row = values[row_number - 1]
        asin = str(row[asin_index]) if asin_index is not None and asin_index < len(row) else ""
        print(f"{sheet}\t{row_number}\t{asin}\t→{destination}")

    if args.dry_run:
        return len(row_numbers)

    plan = plan_transfer(values, repository.read_values(destination), row_numbers)
    repository.ensure_rows(destination, max(plan))
    repository.apply_updates(destination, plan)
    repository.delete_rows(sheet, row_numbers)

    logger.info(
        f"{destination}へ移しました",
        extra={"context": {"sheet": sheet, "rows": len(row_numbers)}},
    )
    return len(row_numbers)


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
