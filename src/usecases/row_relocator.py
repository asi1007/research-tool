from __future__ import annotations

from src.domain.value_objects.asin import Asin


def relocate_updates(
    values: list[list],
    asin_column: int,
    planned: list[tuple[str, dict[int, object]]],
    header_rows: int,
) -> tuple[dict[int, dict[int, object]], list[str], list[str]]:
    """書き込む直前に ASIN で行番号を引き直す。

    読み取りから書き込みまでの間に行が挿入・削除・並び替えされると、読み取り時の
    行番号は別の商品を指す。2026-09-05 に fetch_products で実際に8行ずれた。
    同じ ASIN の行が複数あるときは、どちらを読んだのか決められないので書かない。
    """
    rows: dict[str, list[int]] = {}
    for offset, row in enumerate(values[header_rows:]):
        cell = str(row[asin_column]) if asin_column < len(row) else ""
        asin = Asin.parse(cell)
        if asin is not None:
            rows.setdefault(asin.value, []).append(header_rows + offset + 1)

    updates: dict[int, dict[int, object]] = {}
    missing: list[str] = []
    ambiguous: list[str] = []
    for value, columns in planned:
        found = rows.get(value, [])
        if not found:
            missing.append(value)
        elif len(found) > 1:
            ambiguous.append(value)
        else:
            updates[found[0]] = columns

    return updates, missing, ambiguous
