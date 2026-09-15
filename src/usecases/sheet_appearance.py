from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterator

# 揃えるのは「列ごとに決まる見え方」だけ。背景色は cell_highlighter が
# 「自動で埋めたセル」の印に使っており、textFormat.link は仕入先URLのリンクなので触らない
CELL_FORMAT_FIELDS = ("numberFormat", "horizontalAlignment", "verticalAlignment", "wrapStrategy")
TEXT_FORMAT_FIELDS = ("fontSize", "bold", "foregroundColorStyle")
FORMAT_FIELD_MASK = ",".join(
    [f"userEnteredFormat.{name}" for name in CELL_FORMAT_FIELDS]
    + [f"userEnteredFormat.textFormat.{name}" for name in TEXT_FORMAT_FIELDS]
)
HEADER_ROWS = 3
DEFAULT_ROW_HEIGHT = 21


@dataclass(frozen=True)
class ColumnAppearance:
    width: int
    hidden: bool
    cell_format: dict[str, Any]


@dataclass(frozen=True)
class SheetAppearance:
    columns: list[ColumnAppearance]
    frozen_rows: int
    frozen_columns: int
    header_row_heights: list[int]
    data_row_height: int


def pick_cell_format(cell_format: dict[str, Any]) -> dict[str, Any]:
    picked = {name: cell_format[name] for name in CELL_FORMAT_FIELDS if name in cell_format}
    text_format = cell_format.get("textFormat", {})
    picked_text = {name: text_format[name] for name in TEXT_FORMAT_FIELDS if name in text_format}
    if picked_text:
        picked["textFormat"] = picked_text
    return picked


def build_appearance(
    properties: dict[str, Any],
    column_metadata: list[dict[str, Any]],
    row_metadata: list[dict[str, Any]],
    template_rows: list[list[dict[str, Any]]],
    header_rows: int = HEADER_ROWS,
) -> SheetAppearance:
    grid = properties.get("gridProperties", {})
    return SheetAppearance(
        columns=_build_columns(column_metadata, template_rows),
        frozen_rows=grid.get("frozenRowCount", 0),
        frozen_columns=grid.get("frozenColumnCount", 0),
        header_row_heights=_row_heights(row_metadata[:header_rows]),
        data_row_height=_common_row_height(row_metadata[header_rows:]),
    )


def build_requests(
    appearance: SheetAppearance,
    sheet_id: int,
    row_count: int,
    header_rows: int = HEADER_ROWS,
) -> list[dict[str, Any]]:
    return [
        _freeze_request(appearance, sheet_id),
        *_column_requests(appearance, sheet_id),
        *_row_height_requests(appearance, sheet_id, row_count, header_rows),
        *_cell_format_requests(appearance, sheet_id, row_count, header_rows),
    ]


def _build_columns(
    column_metadata: list[dict[str, Any]],
    template_rows: list[list[dict[str, Any]]],
) -> list[ColumnAppearance]:
    return [
        ColumnAppearance(
            width=metadata.get("pixelSize", 100),
            hidden=bool(metadata.get("hiddenByUser", False)),
            cell_format=_column_format(template_rows, index),
        )
        for index, metadata in enumerate(column_metadata)
    ]


def _column_format(template_rows: list[list[dict[str, Any]]], index: int) -> dict[str, Any]:
    # 見本の行にも書式が抜けた行が混ざるため、1行だけ見ず最頻の書式を採る
    candidates = [
        json.dumps(picked, sort_keys=True)
        for picked in (pick_cell_format(_cell_format(row, index)) for row in template_rows)
        if picked
    ]
    if not candidates:
        return {}
    return json.loads(Counter(candidates).most_common(1)[0][0])


def _cell_format(cells: list[dict[str, Any]], index: int) -> dict[str, Any]:
    if index >= len(cells):
        return {}
    return cells[index].get("userEnteredFormat", {})


def _row_heights(row_metadata: list[dict[str, Any]]) -> list[int]:
    return [metadata.get("pixelSize", DEFAULT_ROW_HEIGHT) for metadata in row_metadata]


def _common_row_height(row_metadata: list[dict[str, Any]]) -> int:
    heights = _row_heights(row_metadata)
    if not heights:
        return DEFAULT_ROW_HEIGHT
    return Counter(heights).most_common(1)[0][0]


def _freeze_request(appearance: SheetAppearance, sheet_id: int) -> dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": appearance.frozen_rows,
                    "frozenColumnCount": appearance.frozen_columns,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def _column_requests(appearance: SheetAppearance, sheet_id: int) -> list[dict[str, Any]]:
    return [
        _dimension_request(
            sheet_id,
            "COLUMNS",
            start,
            end,
            {"pixelSize": column.width, "hiddenByUser": column.hidden},
            "pixelSize,hiddenByUser",
        )
        for start, end, column in _runs(appearance.columns, lambda c: (c.width, c.hidden))
    ]


def _row_height_requests(
    appearance: SheetAppearance,
    sheet_id: int,
    row_count: int,
    header_rows: int,
) -> list[dict[str, Any]]:
    header = [
        _dimension_request(sheet_id, "ROWS", start, end, {"pixelSize": height}, "pixelSize")
        for start, end, height in _runs(appearance.header_row_heights, lambda h: h)
    ]
    if row_count <= header_rows:
        return header
    return header + [
        _dimension_request(
            sheet_id,
            "ROWS",
            header_rows,
            row_count,
            {"pixelSize": appearance.data_row_height},
            "pixelSize",
        )
    ]


def _cell_format_requests(
    appearance: SheetAppearance,
    sheet_id: int,
    row_count: int,
    header_rows: int,
) -> list[dict[str, Any]]:
    if row_count <= header_rows:
        return []
    return [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_rows,
                    "endRowIndex": row_count,
                    "startColumnIndex": start,
                    "endColumnIndex": end,
                },
                "cell": {"userEnteredFormat": column.cell_format},
                "fields": FORMAT_FIELD_MASK,
            }
        }
        for start, end, column in _runs(appearance.columns, lambda c: c.cell_format)
    ]


def _dimension_request(
    sheet_id: int,
    dimension: str,
    start: int,
    end: int,
    properties: dict[str, Any],
    fields: str,
) -> dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": dimension,
                "startIndex": start,
                "endIndex": end,
            },
            "properties": properties,
            "fields": fields,
        }
    }


def _runs(items: list[Any], key: Callable[[Any], Any]) -> Iterator[tuple[int, int, Any]]:
    start = 0
    for index in range(1, len(items) + 1):
        if index < len(items) and key(items[index]) == key(items[start]):
            continue
        yield start, index, items[start]
        start = index
