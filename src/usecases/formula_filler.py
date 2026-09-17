from __future__ import annotations

import re

from src.domain.value_objects.asin import Asin


def rewrite_row(formula: str, source_row: int, target_row: int) -> str:
    # =N4-T4 のような相対参照だけを対象行へずらす。$4 の絶対参照と、
    # 別の行を指す参照（=I4*O40 の O40）は触らない
    return re.sub(
        rf"(?<![$\d])([A-Z]+){source_row}(?!\d)",
        lambda matched: f"{matched.group(1)}{target_row}",
        formula,
    )


_QUOTED = re.compile(r'("[^"]*")')
_CELL_REFERENCE = re.compile(r"(?<![$A-Za-z0-9_.])([A-Z]{1,3})(\d+)(?![\d(A-Za-z_])")


def rebase_formula(
    formula: str, source_row: int, target_row: int, column_map: dict[str, str]
) -> str | None:
    # 別のタブへ移すと行も列の並びも変わる。同じ行を指す相対参照だけを移動先の行・列へ付け替え、
    # 移動先に無い列を指すなら別の値を計算してしまうので書かない
    unmapped = False

    def replace(matched: re.Match) -> str:
        nonlocal unmapped
        letter, row = matched.group(1), int(matched.group(2))
        if row != source_row:
            return matched.group(0)
        if letter not in column_map:
            unmapped = True
            return matched.group(0)
        return f"{column_map[letter]}{target_row}"

    parts = [
        part if _QUOTED.fullmatch(part) else _CELL_REFERENCE.sub(replace, part)
        for part in _QUOTED.split(formula)
    ]
    return None if unmapped else "".join(parts)


def find_template(values: list[list], column: int, header_rows: int) -> tuple[int, str] | None:
    for offset, row in enumerate(values[header_rows:]):
        if column >= len(row):
            continue
        cell = str(row[column])
        if cell.startswith("="):
            return (header_rows + offset + 1, cell)
    return None


def plan_formula_updates(
    values: list[list],
    asin_column: int,
    formula_columns: list[int],
    header_rows: int,
) -> dict[int, dict[int, object]]:
    updates: dict[int, dict[int, object]] = {}

    for column in formula_columns:
        template = find_template(values, column, header_rows)
        if template is None:
            continue
        source_row, formula = template

        for offset, row in enumerate(values[header_rows:]):
            row_number = header_rows + offset + 1
            cell = str(row[asin_column]) if asin_column < len(row) else ""
            if Asin.parse(cell) is None:
                continue
            if column < len(row) and str(row[column]).strip():
                continue
            updates.setdefault(row_number, {})[column] = rewrite_row(formula, source_row, row_number)

    return updates
