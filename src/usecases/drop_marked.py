from __future__ import annotations

import unicodedata

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

DROP_MARK = "d"
MARK_COLUMN_INDEX = 0
ASIN_CODE = "ASIN_SELL"
HEADER_ROWS = 3


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def _is_drop_mark(value: str) -> bool:
    return unicodedata.normalize("NFKC", value).strip().lower() == DROP_MARK


def marked_row_numbers(values: list[list]) -> list[int]:
    asin_index = ColumnCodes(values).index_of(ASIN_CODE)
    if asin_index is None:
        return []

    return [
        HEADER_ROWS + offset + 1
        for offset, row in enumerate(values[HEADER_ROWS:])
        if _is_drop_mark(_cell(row, MARK_COLUMN_INDEX))
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
