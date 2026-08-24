from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.infrastructure.candidate_parser import parse_candidates
from src.infrastructure.cell_highlighter import apply_highlight
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import (
    DEFAULT_HEADER_ROW,
    GoogleSheetRepository,
    SheetTable,
)
from src.usecases.build_supplier_updates import build_updates
from src.usecases.select_supplier_targets import SupplierTarget, select_targets

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

REQUIRED_WRITE_CODES = (
    "LINK_LOWEST", "PRICE_LOWEST", "LOCALPRICE_LOWEST",
    "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "CURRENCY_BUY_OTHER1", "LOCALPRICE_BUY_OTHER1",
    "LINK_BUY_OTHER2", "PRICE_BUY_OTHER2", "CURRENCY_BUY_OTHER2", "LOCALPRICE_BUY_OTHER2",
)


def missing_write_codes(codes: ColumnCodes) -> list[str]:
    return [code for code in REQUIRED_WRITE_CODES if codes.index_of(code) is None]


def reverse_write_codes(codes: ColumnCodes) -> dict[int, str]:
    return {
        index: code
        for code in REQUIRED_WRITE_CODES
        if (index := codes.index_of(code)) is not None
    }


def column_code_names(codes: ColumnCodes, indexes: list[int]) -> list[str]:
    reverse = reverse_write_codes(codes)
    return [reverse.get(index, str(index)) for index in sorted(indexes)]


def read_cell(values: list[list], row_number: int, column_index: int) -> str | None:
    row_position = row_number - 1
    if row_position < 0 or row_position >= len(values):
        return None
    row = values[row_position]
    if column_index >= len(row):
        return None
    return str(row[column_index])


class LinkLowestState(Enum):
    BLANK = "blank"
    OCCUPIED = "occupied"
    ROW_NOT_FOUND = "row_not_found"


def link_lowest_state(values: list[list], row_number: int, link_index: int) -> LinkLowestState:
    cell = read_cell(values, row_number, link_index)
    if cell is None:
        return LinkLowestState.ROW_NOT_FOUND
    if cell.strip() == "":
        return LinkLowestState.BLANK
    return LinkLowestState.OCCUPIED


def header_row_error(row: int, header_row: int) -> str | None:
    if row > header_row:
        return None
    return f"--row はヘッダー行({header_row}行目以下)を指定できません"


def parse_candidates_payload(text: str) -> list:
    raw = json.loads(text)
    if not isinstance(raw, list):
        raise ValueError(f"候補データがリストではありません(type={type(raw).__name__})")
    return raw


def drop_occupied_columns(
    values: list[list], row_number: int, updates: dict[int, object], codes: ColumnCodes
) -> tuple[dict[int, object], dict[str, str]]:
    reverse = reverse_write_codes(codes)
    kept: dict[int, object] = {}
    skipped: dict[str, str] = {}
    for column, value in updates.items():
        existing = (read_cell(values, row_number, column) or "").strip()
        if existing:
            skipped[reverse.get(column, str(column))] = existing
        else:
            kept[column] = value
    return kept, skipped


def describe_candidates(candidates: list[SupplierCandidate]) -> list[dict]:
    return [
        {
            "offer_id": candidate.offer_id.value,
            "title": candidate.title,
            "company": candidate.company,
            "province": candidate.province,
            "local_price": candidate.local_price,
            "quantity": candidate.quantity,
        }
        for candidate in candidates
    ]


class HighlightError(Exception):
    def __init__(self, row: int, columns: list[str]) -> None:
        super().__init__(f"背景色の設定に失敗しました: row={row} columns={columns}")
        self.row = row
        self.columns = columns


def write_and_highlight(
    repository: GoogleSheetRepository,
    worksheet: object,
    sheet: str,
    row: int,
    updates: dict[int, object],
    codes: ColumnCodes,
) -> int:
    written = repository.apply_updates(sheet, {row: updates})
    try:
        apply_highlight(worksheet, [(row, column) for column in updates])
    except Exception as error:
        raise HighlightError(row, column_code_names(codes, list(updates))) from error
    return written


def build_targets_result(
    table: SheetTable, codes: ColumnCodes, limit: int
) -> tuple[list[SupplierTarget], str | None]:
    try:
        return select_targets(table, codes, limit=limit), None
    except ValueError as error:
        return [], str(error)


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

    targets, error = build_targets_result(SheetTable(values), ColumnCodes(values), args.limit)
    if error is not None:
        logger.error("対象行の抽出に失敗しました", extra={"context": {"error": error}})
        return 1

    print(json.dumps([asdict(target) for target in targets], ensure_ascii=False, indent=1))
    logger.info("対象行を抽出しました", extra={"context": {"count": len(targets)}})
    return 0


def run_write(args: argparse.Namespace) -> int:
    header_error = header_row_error(args.row, DEFAULT_HEADER_ROW)
    if header_error:
        logger.error(header_error, extra={"context": {"row": args.row}})
        return 1

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
    state = link_lowest_state(values, args.row, link_index)
    if state is LinkLowestState.ROW_NOT_FOUND:
        logger.error(
            "対象行が見つからないため書き込みません",
            extra={"context": {"row": args.row}},
        )
        return 1
    if state is LinkLowestState.OCCUPIED:
        existing_link = read_cell(values, args.row, link_index)
        logger.error(
            "対象行には既に購入先が入っているため書き込みません",
            extra={"context": {"row": args.row, "existing_link_lowest": existing_link.strip()}},
        )
        return 1

    try:
        raw_items = parse_candidates_payload(Path(args.candidates).read_text(encoding="utf-8"))
    except ValueError as error:
        logger.error(
            "候補データの形式が不正です",
            extra={"context": {"row": args.row, "error": str(error)}},
        )
        return 1

    candidates = parse_candidates(raw_items)
    updates = build_updates(args.row, candidates, codes)

    if not updates:
        logger.warning("候補が無いため書き込みません", extra={"context": {"row": args.row}})
        return 0

    filtered, skipped = drop_occupied_columns(values, args.row, updates, codes)
    if skipped:
        logger.warning(
            "セルに既に値が入っているため一部の列への書き込みをスキップしました",
            extra={"context": {"row": args.row, "skipped_columns": skipped}},
        )

    if not filtered:
        logger.warning(
            "対象列にすべて既に値が入っているため書き込みません",
            extra={"context": {"row": args.row}},
        )
        return 0

    try:
        write_and_highlight(repository, worksheet, args.sheet, args.row, filtered, codes)
    except HighlightError as error:
        logger.error(
            "背景色の設定に失敗しました(値は書き込み済みです)",
            extra={"context": {"row": error.row, "written_columns": error.columns}},
        )
        return 1

    logger.info(
        "仕入先候補を書き込みました",
        extra={
            "context": {
                "row": args.row,
                "cells": len(filtered),
                "candidates": describe_candidates(candidates),
            }
        },
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
