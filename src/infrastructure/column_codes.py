from __future__ import annotations

from src.infrastructure.column_mapper import normalize_header

CODE_ROW = 1


class ColumnCodes:
    def __init__(self, values: list[list], code_row: int = CODE_ROW) -> None:
        row = values[code_row - 1] if len(values) >= code_row else []
        self._index = {
            normalize_header(cell): position
            for position, cell in enumerate(row)
            if normalize_header(cell)
        }

    def index_of(self, code: str) -> int | None:
        return self._index.get(code)
