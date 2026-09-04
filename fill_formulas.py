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
from src.infrastructure.sheet_repository import (
    DEFAULT_HEADER_ROW,
    GoogleSheetRepository,
    SheetTable,
    column_letter,
)
from src.usecases.formula_filler import plan_formula_updates

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

ASIN_CODE = "ASIN_SELL"
# 取得した値からは決まらない数式列。既存行の式をコピーして相対参照だけずらす
FORMULA_HEADERS = ("月間販売高", "利益", "利益率")


def normalize_header(label: object) -> str:
    return str(label or "").replace("\n", "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="月間販売高・利益・利益率の数式を空欄行へ入れる")
    parser.add_argument("--sheet", action="append", help="対象タブ（省略時は自動調査タブすべて）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    load_dotenv(PROJECT_ROOT / ".env")
    repository = GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )

    sheets = args.sheet or discovery_sheets(repository.sheet_titles())
    total = 0

    for sheet in sheets:
        values = repository.read_values(sheet)
        asin_index = ColumnCodes(values).index_of(ASIN_CODE)
        if asin_index is None:
            logger.warning("ASIN列がありません", extra={"context": {"sheet": sheet}})
            continue

        headers = {normalize_header(h): i for i, h in enumerate(SheetTable(values).headers)}
        columns = [headers[name] for name in FORMULA_HEADERS if name in headers]
        updates = plan_formula_updates(
            values, asin_column=asin_index, formula_columns=columns, header_rows=DEFAULT_HEADER_ROW
        )

        count = sum(len(cells) for cells in updates.values())
        total += count
        print(
            f"{sheet}: {count}セル "
            f"({', '.join(f'{n}={column_letter(headers[n])}' for n in FORMULA_HEADERS if n in headers)})"
        )
        if args.dry_run or not updates:
            continue

        repository.apply_updates(sheet, updates)

    print(f"\n合計 {total} セル")
    return 0


if __name__ == "__main__":
    sys.exit(main())
