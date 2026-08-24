from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.candidate_parser import parse_candidates
from src.infrastructure.cell_highlighter import apply_highlight
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository, SheetTable
from src.usecases.build_supplier_updates import build_updates
from src.usecases.select_supplier_targets import select_targets

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

REQUIRED_WRITE_CODES = (
    "LINK_LOWEST", "PRICE_LOWEST", "LOCALPRICE_LOWEST",
    "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "CURRENCY_BUY_OTHER1", "LOCALPRICE_BUY_OTHER1",
    "LINK_BUY_OTHER2", "PRICE_BUY_OTHER2", "CURRENCY_BUY_OTHER2", "LOCALPRICE_BUY_OTHER2",
)


def missing_write_codes(codes: ColumnCodes) -> list[str]:
    return [code for code in REQUIRED_WRITE_CODES if codes.index_of(code) is None]


def read_cell(values: list[list], row_number: int, column_index: int) -> str | None:
    row_position = row_number - 1
    if row_position < 0 or row_position >= len(values):
        return None
    row = values[row_position]
    if column_index >= len(row):
        return None
    return str(row[column_index])


def is_link_lowest_blank(values: list[list], row_number: int, link_index: int) -> bool:
    cell = read_cell(values, row_number, link_index)
    return cell is not None and cell.strip() == ""


def build_repository() -> GoogleSheetRepository:
    load_dotenv(PROJECT_ROOT / ".env")
    return GoogleSheetRepository(
        str(PROJECT_ROOT / os.environ["SERVICE_ACCOUNT_FILE"]),
        os.environ["RESEARCH_SPREADSHEET_ID"],
    )


def read_values(repository: GoogleSheetRepository, sheet_name: str) -> tuple[list[list], object]:
    worksheet = repository.spreadsheet.worksheet(sheet_name)
    return worksheet.get_values(value_render_option="FORMULA"), worksheet


def run_targets(args: argparse.Namespace) -> int:
    repository = build_repository()
    values, _ = read_values(repository, args.sheet)

    targets = select_targets(SheetTable(values), ColumnCodes(values), limit=args.limit)

    print(json.dumps([asdict(target) for target in targets], ensure_ascii=False, indent=1))
    logger.info("対象行を抽出しました", extra={"context": {"count": len(targets)}})
    return 0


def run_write(args: argparse.Namespace) -> int:
    repository = build_repository()
    values, worksheet = read_values(repository, args.sheet)
    codes = ColumnCodes(values)

    missing = missing_write_codes(codes)
    if missing:
        logger.error(
            "1行目に列コードが見つかりません",
            extra={"context": {"missing_codes": missing}},
        )
        return 1

    link_index = codes.index_of("LINK_LOWEST")
    existing_link = read_cell(values, args.row, link_index)
    if existing_link is None:
        logger.error(
            "対象行が見つからないため書き込みません",
            extra={"context": {"row": args.row}},
        )
        return 1
    if existing_link.strip() != "":
        logger.error(
            "対象行には既に購入先が入っているため書き込みません",
            extra={"context": {"row": args.row, "existing_link_lowest": existing_link.strip()}},
        )
        return 1

    raw_items = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    candidates = parse_candidates(raw_items)
    updates = build_updates(args.row, candidates, codes)

    if not updates:
        logger.warning("候補が無いため書き込みません", extra={"context": {"row": args.row}})
        return 0

    repository.apply_updates(args.sheet, {args.row: updates})
    apply_highlight(worksheet, [(args.row, column) for column in updates])

    logger.info(
        "仕入先候補を書き込みました",
        extra={"context": {"row": args.row, "cells": len(updates)}},
    )
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    targets = subparsers.add_parser("targets")
    targets.add_argument("--sheet", required=True)
    targets.add_argument("--limit", type=int, default=10)
    targets.set_defaults(func=run_targets)

    write = subparsers.add_parser("write")
    write.add_argument("--sheet", required=True)
    write.add_argument("--row", type=int, required=True)
    write.add_argument("--candidates", required=True)
    write.set_defaults(func=run_write)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
