from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from src.domain.entities.product_info import ProductInfo
from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_criteria import (
    EXCLUDED_BRANDS,
    EXCLUDED_MAKERS,
    DiscoveryCriteria,
)
from src.infrastructure.column_codes import ColumnCodes

ASIN_CODE = "ASIN_SELL"
NOTE_CODE = "NOTE_BUY_OTHER2"
NOTE_PREFIX = "自動調査"
HEADER_ROWS = 3
_BRAND_SEPARATORS = re.compile(r"[()\[\]（）【】/／]")


def known_asins(sheet_values: dict[str, list[list]]) -> set[str]:
    collected: set[str] = set()

    for values in sheet_values.values():
        asin_index = ColumnCodes(values).index_of(ASIN_CODE)
        if asin_index is None:
            continue

        for row in values[HEADER_ROWS:]:
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
        if limit is not None and len(selected) >= limit:
            break
        if str(asin) in seen:
            continue
        seen.add(str(asin))
        selected.append(asin)

    return selected


def select_by_revenue(
    products: list[ProductInfo], criteria: DiscoveryCriteria
) -> list[Asin]:
    return [
        product.asin
        for product in products
        if criteria.meets_revenue(product.buy_box_price, product.monthly_sold)
        and not _is_excluded_category(product, criteria)
        and not _is_excluded_brand(product)
    ]


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().lower()


def _brand_names(brand_field: str) -> set[str]:
    # 「トンボ(Tombow)」「IKEA (イケア)」のように日本語と英字が括弧で併記される
    normalized = _normalize(brand_field)
    parts = {part.strip() for part in _BRAND_SEPARATORS.split(normalized)}
    return {normalized, *parts} - {""}


def _is_excluded_brand(product: ProductInfo) -> bool:
    brand_fields = [field for field in (product.brand, product.manufacturer) if field.strip()]
    if brand_fields:
        excluded = {_normalize(brand) for brand in EXCLUDED_BRANDS + EXCLUDED_MAKERS}
        return any(_brand_names(field) & excluded for field in brand_fields)

    # ブランド欄が無いときだけ商品名で探す。互換品の説明に反応するので、有名ブランドは探さない
    title = _normalize(product.title)
    return any(_normalize(brand) in title for brand in EXCLUDED_BRANDS)


def _is_excluded_category(product: ProductInfo, criteria: DiscoveryCriteria) -> bool:
    # Keepa の categories_exclude は categoryTree を見るので、ツリーが空の商品は
    # クエリで弾けない。実測した rootCategory でもう一度ふるいにかける
    return product.root_category in criteria.excluded_categories


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
        HEADER_ROWS + offset + 1
        for offset, row in enumerate(values[HEADER_ROWS:])
        if _is_blank(row, asin_index)
    ]

    updates: dict[int, dict[int, object]] = {}
    next_row = max(len(values), HEADER_ROWS) + 1
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
