from __future__ import annotations

import logging

import gspread
from google.oauth2.service_account import Credentials

from src.infrastructure.column_mapper import normalize_header

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
DEFAULT_HEADER_ROW = 3
# IMAGE() や HYPERLINK() のセルは表示値が空になるため、数式のまま読まないと空欄と誤判定する
FORMULA_RENDER_OPTION = "FORMULA"


def column_letter(index: int) -> str:
    letters = ""
    remainder = index + 1
    while remainder > 0:
        remainder, modulo = divmod(remainder - 1, 26)
        letters = chr(ord("A") + modulo) + letters
    return letters


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
        worksheet = self.spreadsheet.worksheet(sheet_name)
        values = worksheet.get_values(value_render_option=FORMULA_RENDER_OPTION)
        return SheetTable(values, header_row=header_row)

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
