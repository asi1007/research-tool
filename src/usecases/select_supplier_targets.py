from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.image_formula import extract_image_url
from src.infrastructure.sheet_repository import SheetTable

DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class SupplierTarget:
    row_number: int
    asin: str
    image_url: str


def _cell(row: list, index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index]).strip()


def select_targets(
    table: SheetTable, codes: ColumnCodes, limit: int = DEFAULT_LIMIT
) -> list[SupplierTarget]:
    asin_index = codes.index_of("ASIN_SELL")
    image_index = codes.index_of("IMAGE")
    link_index = codes.index_of("LINK_LOWEST")

    if link_index is None:
        raise ValueError("1行目に列コードが見つかりません: LINK_LOWEST")
    if image_index is None:
        raise ValueError("1行目に列コードが見つかりません: IMAGE")

    targets: list[SupplierTarget] = []

    for data_index, row in enumerate(table.data_rows):
        if len(targets) >= limit:
            break
        if _cell(row, link_index):
            continue

        image_url = extract_image_url(_cell(row, image_index))
        if not image_url:
            continue

        targets.append(
            SupplierTarget(
                row_number=table.row_number(data_index),
                asin=_cell(row, asin_index),
                image_url=image_url,
            )
        )

    return targets
