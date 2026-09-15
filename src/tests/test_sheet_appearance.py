from __future__ import annotations

from src.usecases.sheet_appearance import (
    FORMAT_FIELD_MASK,
    ColumnAppearance,
    SheetAppearance,
    build_appearance,
    build_requests,
    pick_cell_format,
)

PROPERTIES = {"gridProperties": {"frozenRowCount": 3, "frozenColumnCount": 3}}


def test_pick_cell_format_keeps_only_column_wide_appearance():
    picked = pick_cell_format(
        {
            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            "horizontalAlignment": "RIGHT",
            "backgroundColor": {"red": 0.929, "green": 0.929, "blue": 0.929},
            "textFormat": {"fontSize": 9, "link": {"uri": "https://example.com"}},
        }
    )

    assert picked == {
        "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
        "horizontalAlignment": "RIGHT",
        "textFormat": {"fontSize": 9},
    }


def test_pick_cell_format_drops_empty_text_format():
    assert pick_cell_format({"textFormat": {"link": {"uri": "https://example.com"}}}) == {}


def test_build_appearance_reads_widths_frozen_and_common_data_row_height():
    appearance = build_appearance(
        properties=PROPERTIES,
        column_metadata=[{"pixelSize": 21}, {"pixelSize": 83, "hiddenByUser": True}],
        row_metadata=[{"pixelSize": 24}, {"pixelSize": 21}, {"pixelSize": 21}]
        + [{"pixelSize": 42}, {"pixelSize": 42}, {"pixelSize": 60}],
        template_rows=[[{}, {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}}]],
    )

    assert appearance.columns == [
        ColumnAppearance(width=21, hidden=False, cell_format={}),
        ColumnAppearance(width=83, hidden=True, cell_format={"numberFormat": {"type": "TEXT"}}),
    ]
    assert (appearance.frozen_rows, appearance.frozen_columns) == (3, 3)
    assert appearance.header_row_heights == [24, 21, 21]
    assert appearance.data_row_height == 42


def test_build_appearance_takes_the_most_common_format_across_template_rows():
    bold = {"userEnteredFormat": {"textFormat": {"bold": True}}}
    plain = {"userEnteredFormat": {"textFormat": {"bold": False}}}
    appearance = build_appearance(
        properties=PROPERTIES,
        column_metadata=[{"pixelSize": 33}],
        row_metadata=[{"pixelSize": 24}, {"pixelSize": 21}, {"pixelSize": 21}, {"pixelSize": 42}],
        template_rows=[[{}], [bold], [plain], [bold]],
    )

    assert appearance.columns[0].cell_format == {"textFormat": {"bold": True}}


def test_build_appearance_falls_back_when_template_row_is_shorter_than_the_sheet():
    appearance = build_appearance(
        properties=PROPERTIES,
        column_metadata=[{"pixelSize": 33}, {"pixelSize": 33}],
        row_metadata=[{"pixelSize": 24}, {"pixelSize": 21}, {"pixelSize": 21}, {"pixelSize": 42}],
        template_rows=[[{"userEnteredFormat": {"wrapStrategy": "OVERFLOW_CELL"}}]],
    )

    assert appearance.columns[1].cell_format == {}


def _appearance(columns: list[ColumnAppearance]) -> SheetAppearance:
    return SheetAppearance(
        columns=columns,
        frozen_rows=3,
        frozen_columns=3,
        header_row_heights=[24, 21, 21],
        data_row_height=42,
    )


def test_build_requests_groups_adjacent_columns_that_look_the_same():
    columns = [
        ColumnAppearance(width=33, hidden=False, cell_format={"horizontalAlignment": "RIGHT"}),
        ColumnAppearance(width=33, hidden=False, cell_format={"horizontalAlignment": "RIGHT"}),
        ColumnAppearance(width=67, hidden=True, cell_format={"horizontalAlignment": "RIGHT"}),
    ]

    requests = build_requests(_appearance(columns), sheet_id=7, row_count=100)
    dimensions = [r["updateDimensionProperties"] for r in requests if "updateDimensionProperties" in r]
    column_ranges = [
        (d["range"]["startIndex"], d["range"]["endIndex"], d["properties"])
        for d in dimensions
        if d["range"]["dimension"] == "COLUMNS"
    ]

    assert column_ranges == [
        (0, 2, {"pixelSize": 33, "hiddenByUser": False}),
        (2, 3, {"pixelSize": 67, "hiddenByUser": True}),
    ]


def test_build_requests_freezes_and_sizes_rows():
    requests = build_requests(_appearance([ColumnAppearance(33, False, {})]), sheet_id=7, row_count=100)

    assert requests[0]["updateSheetProperties"]["properties"]["gridProperties"] == {
        "frozenRowCount": 3,
        "frozenColumnCount": 3,
    }
    row_ranges = [
        (d["range"]["startIndex"], d["range"]["endIndex"], d["properties"]["pixelSize"])
        for d in (r["updateDimensionProperties"] for r in requests if "updateDimensionProperties" in r)
        if d["range"]["dimension"] == "ROWS"
    ]
    assert row_ranges == [(0, 1, 24), (1, 3, 21), (3, 100, 42)]


def test_build_requests_formats_data_rows_only():
    columns = [
        ColumnAppearance(width=33, hidden=False, cell_format={"numberFormat": {"type": "TEXT"}}),
        ColumnAppearance(width=33, hidden=False, cell_format={}),
    ]

    repeats = [r["repeatCell"] for r in build_requests(_appearance(columns), 7, 100) if "repeatCell" in r]

    assert [(r["range"]["startColumnIndex"], r["range"]["endColumnIndex"]) for r in repeats] == [(0, 1), (1, 2)]
    assert all(r["range"]["startRowIndex"] == 3 and r["range"]["endRowIndex"] == 100 for r in repeats)
    assert all(r["fields"] == FORMAT_FIELD_MASK for r in repeats)
    assert repeats[1]["cell"]["userEnteredFormat"] == {}


def test_build_requests_skips_data_rows_when_the_sheet_has_none():
    requests = build_requests(_appearance([ColumnAppearance(33, False, {})]), sheet_id=7, row_count=3)

    assert not [r for r in requests if "repeatCell" in r]
