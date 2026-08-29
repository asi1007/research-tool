from __future__ import annotations

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

DISCOVERY_SHEET = "自動調査"
ASIN_CODE = "ASIN_SELL"
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
