from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

DISCOVERY_SHEET = "自動調査"
ASIN_CODE = "ASIN_SELL"
NOTE_CODE = "NOTE_BUY_OTHER2"
NOTE_PREFIX = "自動調査"
DATA_START_ROW = 3


def known_asins(sheet_values: dict[str, list[list]]) -> set[str]:
    collected: set[str] = set()

    for values in sheet_values.values():
        asin_index = ColumnCodes(values).index_of(ASIN_CODE)
        if asin_index is None:
            continue

        for row in values[DATA_START_ROW:]:
            if asin_index >= len(row):
                continue
            asin = Asin.parse(row[asin_index])
            if asin is not None:
                collected.add(str(asin))

    return collected


def select_new_asins(
    found: list[Asin], known: set[str], limit: int | None = None
) -> list[Asin]:
    selected: list[Asin] = []
    seen = set(known)

    for asin in found:
        if str(asin) in seen:
            continue
        seen.add(str(asin))
        selected.append(asin)
        if limit is not None and len(selected) >= limit:
            break

    return selected


@dataclass(frozen=True)
class AppendPlan:
    updates: dict[int, dict[int, object]]
    rows_to_add: int


def _is_blank(row: list, index: int) -> bool:
    return index >= len(row) or not str(row[index]).strip()


def plan_append(values: list[list], asins: list[Asin], discovered_on: date) -> AppendPlan:
    if not asins:
        return AppendPlan(updates={}, rows_to_add=0)

    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    note_index = codes.index_of(NOTE_CODE)
    if asin_index is None or note_index is None:
        raise ValueError(f"1行目に列コードが見つかりません: {ASIN_CODE} / {NOTE_CODE}")

    note = f"{NOTE_PREFIX}{discovered_on.isoformat()}"
    blank_rows = [
        DATA_START_ROW + offset + 1
        for offset, row in enumerate(values[DATA_START_ROW:])
        if _is_blank(row, asin_index)
    ]

    updates: dict[int, dict[int, object]] = {}
    next_row = len(values) + 1
    rows_to_add = 0

    for position, asin in enumerate(asins):
        if position < len(blank_rows):
            row_number = blank_rows[position]
        else:
            row_number = next_row
            next_row += 1
            rows_to_add += 1
        updates[row_number] = {asin_index: str(asin), note_index: note}

    return AppendPlan(updates=updates, rows_to_add=rows_to_add)
