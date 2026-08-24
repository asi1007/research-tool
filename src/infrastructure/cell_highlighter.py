from __future__ import annotations

from src.infrastructure.sheet_repository import column_letter

# 自動で埋めたセルを手入力と区別するための薄いグレー (#EDEDED)
FILLED_BACKGROUND = {"red": 0.929, "green": 0.929, "blue": 0.929}


def build_highlight_requests(cells: list[tuple[int, int]]) -> list[dict]:
    return [
        {
            "range": f"{column_letter(column)}{row_number}",
            "format": {"backgroundColor": FILLED_BACKGROUND},
        }
        for row_number, column in sorted(cells)
    ]


def apply_highlight(worksheet, cells: list[tuple[int, int]]) -> int:
    requests = build_highlight_requests(cells)
    if not requests:
        return 0

    worksheet.batch_format(requests)
    return len(requests)
