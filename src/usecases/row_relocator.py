from __future__ import annotations

from src.domain.value_objects.asin import Asin


def relocate_updates(
    values: list[list],
    asin_column: int,
    planned: list[tuple[str, dict[int, object]]],
    header_rows: int,
) -> tuple[dict[int, dict[int, object]], list[str]]:
    """書き込む直前に ASIN で行番号を引き直す。

    読み取りから書き込みまでの間に行が挿入・削除されると、読み取り時の行番号は
    別の商品を指す。2026-09-05 に fetch_products で実際に8行ずれた。
    """
    index: dict[str, int] = {}
    for offset, row in enumerate(values[header_rows:]):
        cell = str(row[asin_column]) if asin_column < len(row) else ""
        asin = Asin.parse(cell)
        if asin is not None and asin.value not in index:
            index[asin.value] = header_rows + offset + 1

    updates: dict[int, dict[int, object]] = {}
    missing: list[str] = []
    for value, columns in planned:
        row_number = index.get(value)
        if row_number is None:
            missing.append(value)
            continue
        updates[row_number] = columns

    return updates, missing
