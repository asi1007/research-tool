from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.domain.value_objects.asin import Asin
from src.infrastructure.sheet_repository import column_letter


class MoveDestination(Enum):
    TOP = "top"
    BOTTOM = "bottom"


@dataclass(frozen=True)
class MovePlan:
    insert_at: int
    updates: dict[int, dict[int, object]]
    source_rows: list[int]
    missing_asins: list[str]
    dropped_codes: list[str]

    @property
    def row_count(self) -> int:
        return len(self.updates)


def _codes(values: list[list]) -> list[str]:
    return [str(cell).strip() for cell in values[0]] if values else []


def _index_of(codes: list[str], code: str) -> int | None:
    return codes.index(code) if code in codes else None


def locate_rows(values: list[list], asin_column: int, asins: list[str]) -> dict[str, int]:
    wanted = {a.upper() for a in asins}
    found: dict[str, int] = {}
    for number, row in enumerate(values, start=1):
        cell = str(row[asin_column]) if asin_column < len(row) else ""
        parsed = Asin.parse(cell)
        if parsed and parsed.value in wanted and parsed.value not in found:
            found[parsed.value] = number
    return found


def missing_codes(source_codes: list[str], dest_codes: list[str]) -> list[str]:
    present = {code for code in dest_codes if code.strip()}
    return [code for code in source_codes if code.strip() and code not in present]


def map_row_to_destination(
    row: list, source_codes: list[str], dest_codes: list[str], source_row: int, dest_row: int
) -> dict[int, object]:
    # 列の並びはシートごとに違う。列コードで対応させ、数式の列レターも読み替える
    letter_map = {
        column_letter(source_index): column_letter(dest_index)
        for source_index, code in enumerate(source_codes)
        if code.strip() and (dest_index := _index_of(dest_codes, code)) is not None
    }

    mapped: dict[int, object] = {}
    for source_index, cell in enumerate(row):
        if not str(cell).strip():
            continue
        code = source_codes[source_index] if source_index < len(source_codes) else ""
        dest_index = _index_of(dest_codes, code) if code.strip() else None
        if dest_index is None:
            continue
        mapped[dest_index] = _rewrite(str(cell), source_row, dest_row, letter_map) \
            if str(cell).startswith("=") else cell
    return mapped


def _rewrite(formula: str, source_row: int, dest_row: int, letter_map: dict[str, str]) -> str:
    # 列レターと行番号を一度に置き換える。先に行だけ直すと、列を直すときに
    # 置換後の参照をもう一度拾ってしまう
    def replace(matched: re.Match) -> str:
        letter, row = matched.group(1), matched.group(2)
        if int(row) != source_row:
            return matched.group(0)
        return f"{letter_map.get(letter, letter)}{dest_row}"

    return re.sub(r"(?<![$\d\w])([A-Z]+)(\d+)(?!\d)", replace, formula)


def build_move_plan(
    source_values: list[list],
    dest_values: list[list],
    asins: list[str],
    destination: MoveDestination,
    header_rows: int,
) -> MovePlan:
    source_codes = _codes(source_values)
    dest_codes = _codes(dest_values)
    asin_column = _index_of(source_codes, "ASIN_SELL")
    if asin_column is None:
        raise ValueError("移動元に ASIN_SELL の列がありません")

    rank_column = _index_of(source_codes, "RIVAL_RANK")
    located = locate_rows(source_values, asin_column, asins)

    rows: list[int] = []
    for asin in asins:
        number = located.get(asin.upper())
        if number is None or number in rows:
            continue
        rows.append(number)
        rows.extend(_rival_rows(source_values, number, asin_column, rank_column, rows))

    insert_at = header_rows + 1 if destination is MoveDestination.TOP else _next_row(dest_values, header_rows)
    updates = {
        insert_at + offset: map_row_to_destination(
            source_values[number - 1], source_codes, dest_codes, number, insert_at + offset
        )
        for offset, number in enumerate(rows)
    }

    return MovePlan(
        insert_at=insert_at,
        updates=updates,
        source_rows=rows,
        missing_asins=[a for a in asins if a.upper() not in located],
        dropped_codes=missing_codes(source_codes, dest_codes),
    )


def _rival_rows(
    values: list[list], number: int, asin_column: int, rank_column: int | None, taken: list[int]
) -> list[int]:
    # 自社行の直下に順位付きの行が続く。まとめて運ばないと親と切り離される
    if rank_column is None:
        return []
    own = values[number - 1]
    if str(own[rank_column]).strip() if rank_column < len(own) else "":
        return []

    found = []
    for candidate in range(number + 1, len(values) + 1):
        row = values[candidate - 1]
        cell = lambda index: (str(row[index]) if index < len(row) else "").strip()
        if not Asin.parse(cell(asin_column)) or not cell(rank_column):
            break
        if candidate not in taken:
            found.append(candidate)
    return found


def _next_row(values: list[list], header_rows: int) -> int:
    for offset in range(len(values), header_rows, -1):
        if any(str(cell).strip() for cell in values[offset - 1]):
            return offset + 1
    return header_rows + 1
