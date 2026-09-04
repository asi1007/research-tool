from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import absolute_range_name

from src.infrastructure.column_mapper import normalize_header

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DEFAULT_HEADER_ROW = 3
# 1行目は列コード（見出しと違い並べ替えや改名の影響を受けない識別子）
CODE_ROW = 1
# IMAGE() や HYPERLINK() のセルは表示値が空になるため、数式のまま読まないと空欄と誤判定する
FORMULA_RENDER_OPTION = "FORMULA"


def column_letter(index: int) -> str:
    letters = ""
    remainder = index + 1
    while remainder > 0:
        remainder, modulo = divmod(remainder - 1, 26)
        letters = chr(ord("A") + modulo) + letters
    return letters


def last_filled_row(values: list[list]) -> int:
    for row_number in range(len(values), 0, -1):
        if any(str(cell).strip() for cell in values[row_number - 1]):
            return row_number
    return 0


def plan_append_rows(values: list[list], rows: list[list]) -> dict[int, dict[int, object]]:
    # gspread の append_rows は表の左端をシート側が判定するため、右へずれて書かれることがある。
    # 行番号と列位置を自分で決めて書く
    start = last_filled_row(values)
    return {
        start + offset + 1: {
            index: cell for index, cell in enumerate(row) if str(cell).strip()
        }
        for offset, row in enumerate(rows)
    }


class SheetTable:
    def __init__(self, values: list[list], header_row: int = DEFAULT_HEADER_ROW) -> None:
        self.header_row = header_row
        self.headers = self._build_headers(values, header_row)
        self.data_rows = values[header_row:] if len(values) > header_row else []

    def _build_headers(self, values: list[list], header_row: int) -> list[str]:
        primary = values[header_row - 1] if len(values) >= header_row else []
        fallback = values[header_row - 2] if header_row >= 2 and len(values) >= header_row - 1 else []

        width = max(len(primary), len(fallback))
        return [
            normalize_header(primary[i] if i < len(primary) else "")
            or normalize_header(fallback[i] if i < len(fallback) else "")
            for i in range(width)
        ]

    def row_number(self, data_index: int) -> int:
        return self.header_row + 1 + data_index


class GoogleSheetRepository:
    def __init__(self, service_account_file: str, spreadsheet_id: str) -> None:
        credentials = Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        self.client = gspread.authorize(credentials)
        self.spreadsheet = self.client.open_by_key(spreadsheet_id)

    def sheet_titles(self) -> list[str]:
        return [worksheet.title for worksheet in self.spreadsheet.worksheets()]

    def read_table(self, sheet_name: str, header_row: int = DEFAULT_HEADER_ROW) -> SheetTable:
        return SheetTable(self.read_values(sheet_name), header_row=header_row)

    def read_values(self, sheet_name: str) -> list[list]:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        return worksheet.get_values(value_render_option=FORMULA_RENDER_OPTION)

    def read_all_values(self) -> dict[str, list[list]]:
        titles = self.sheet_titles()
        ranges = [absolute_range_name(title) for title in titles]
        response = self.spreadsheet.values_batch_get(
            ranges, params={"valueRenderOption": FORMULA_RENDER_OPTION}
        )
        return {
            title: value_range.get("values", [])
            for title, value_range in zip(titles, response["valueRanges"])
        }

    def ensure_rows(self, sheet_name: str, last_row_number: int) -> int:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        shortage = last_row_number - worksheet.row_count
        if shortage <= 0:
            return 0

        worksheet.add_rows(shortage)
        logger.info(
            "行を追加しました",
            extra={"context": {"sheet": sheet_name, "added": shortage}},
        )
        return shortage

    def apply_updates(self, sheet_name: str, updates: dict[int, dict[int, object]]) -> int:
        if not updates:
            return 0

        worksheet = self.spreadsheet.worksheet(sheet_name)
        payload = [
            {
                "range": f"{column_letter(column)}{row_number}",
                "values": [[value]],
            }
            for row_number, columns in sorted(updates.items())
            for column, value in sorted(columns.items())
        ]

        worksheet.batch_update(payload, value_input_option="USER_ENTERED")
        return len(payload)

    def append_rows(self, sheet_name: str, rows: list[list]) -> int:
        updates = plan_append_rows(self.read_values(sheet_name), rows)
        if not updates:
            return 0

        self.ensure_rows(sheet_name, max(updates))
        self.apply_updates(sheet_name, updates)
        logger.info(
            "行を追記しました",
            extra={"context": {"sheet": sheet_name, "rows": len(updates)}},
        )
        return len(updates)

    def insert_rows_at(self, sheet_name: str, start_row: int, count: int) -> int:
        if count <= 0:
            return 0

        worksheet = self.spreadsheet.worksheet(sheet_name)
        # 数式の相対参照を下の行から引き継がせたいので、直前の行の書式を継承する
        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "ROWS",
                                "startIndex": start_row - 1,
                                "endIndex": start_row - 1 + count,
                            },
                            "inheritFromBefore": True,
                        }
                    }
                ]
            }
        )
        logger.info(
            "行を挿入しました",
            extra={"context": {"sheet": sheet_name, "start_row": start_row, "count": count}},
        )
        return count

    def insert_column_at(self, sheet_name: str, index: int, header: str, code: str) -> int:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": index,
                                "endIndex": index + 1,
                            },
                            "inheritFromBefore": False,
                        }
                    }
                ]
            }
        )
        letter = column_letter(index)
        worksheet.batch_update(
            [
                {"range": f"{letter}{CODE_ROW}", "values": [[code]]},
                {"range": f"{letter}{DEFAULT_HEADER_ROW}", "values": [[header]]},
            ],
            value_input_option="USER_ENTERED",
        )
        logger.info(
            "列を挿入しました",
            extra={"context": {"sheet": sheet_name, "column": letter, "code": code}},
        )
        return index

    def delete_rows(self, sheet_name: str, row_numbers: list[int]) -> int:
        if not row_numbers:
            return 0

        worksheet = self.spreadsheet.worksheet(sheet_name)
        # 上から消すと以降の行番号がずれるため、必ず下から消す
        for row_number in sorted(set(row_numbers), reverse=True):
            worksheet.delete_rows(row_number)

        logger.info(
            "行を削除しました",
            extra={"context": {"sheet": sheet_name, "rows": len(set(row_numbers))}},
        )
        return len(set(row_numbers))
