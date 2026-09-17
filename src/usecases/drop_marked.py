from __future__ import annotations

import unicodedata

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import column_letter, last_filled_row
from src.usecases.formula_filler import rebase_formula
from src.usecases.seasonal import SEASONAL_SHEET

DROP_MARK = "d"
SEASONAL_MARK = "s"
PENDING_MARK = "p"
REJECTED_SHEET = "候補外"
PENDING_SHEET = "保留"
# A列の印ごとの移動先。どのタブも既知ASINの突合対象なので、移した商品は二度と積まれない
MARK_DESTINATIONS: dict[str, str] = {
    DROP_MARK: REJECTED_SHEET,
    SEASONAL_MARK: SEASONAL_SHEET,
    PENDING_MARK: PENDING_SHEET,
}
MARK_COLUMN_INDEX = 0
ASIN_CODE = "ASIN_SELL"
HEADER_ROWS = 3


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def _has_mark(value: str, mark: str) -> bool:
    return unicodedata.normalize("NFKC", value).strip().lower() == mark


def marked_row_numbers(values: list[list], mark: str = DROP_MARK) -> list[int]:
    asin_index = ColumnCodes(values).index_of(ASIN_CODE)
    if asin_index is None:
        return []

    return [
        HEADER_ROWS + offset + 1
        for offset, row in enumerate(values[HEADER_ROWS:])
        if _has_mark(_cell(row, MARK_COLUMN_INDEX), mark)
        and Asin.parse(_cell(row, asin_index)) is not None
    ]


def build_transfer_rows(
    values: list[list], target_values: list[list], row_numbers: list[int]
) -> list[list]:
    # 元タブと移送先で列の並びが違うため、列コードで対応付けて詰め替える
    source_codes = ColumnCodes(values)
    target_code_row = target_values[0] if target_values else []

    rows: list[list] = []
    for row_number in row_numbers:
        row = values[row_number - 1]
        rows.append(
            [
                _cell(row, index) if (index := source_codes.index_of(str(code))) is not None else ""
                for code in target_code_row
            ]
        )
    return rows


def _column_letter_map(values: list[list], target_values: list[list]) -> dict[str, str]:
    source_codes = values[0] if values else []
    target_codes = ColumnCodes(target_values)
    return {
        column_letter(index): column_letter(target_index)
        for index, code in enumerate(source_codes)
        if (target_index := target_codes.index_of(str(code))) is not None
    }


def plan_transfer(
    values: list[list], target_values: list[list], row_numbers: list[int]
) -> dict[int, dict[int, object]]:
    # 行番号は移動先を書く直前に読んだ target_values から決める。先に読んだものを使い回すと、
    # 別のタブから移した行を上書きする
    column_map = _column_letter_map(values, target_values)
    start = last_filled_row(target_values)
    plan: dict[int, dict[int, object]] = {}

    for offset, (row_number, row) in enumerate(
        zip(row_numbers, build_transfer_rows(values, target_values, row_numbers))
    ):
        target_row = start + offset + 1
        cells: dict[int, object] = {}
        for index, cell in enumerate(row):
            if not str(cell).strip():
                continue
            if str(cell).startswith("="):
                rebased = rebase_formula(str(cell), row_number, target_row, column_map)
                if rebased is None:
                    continue
                cell = rebased
            cells[index] = cell
        plan[target_row] = cells

    return plan
