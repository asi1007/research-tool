from __future__ import annotations

from find_supplier import REQUIRED_WRITE_CODES, missing_write_codes
from src.infrastructure.column_codes import ColumnCodes


class TestMissingWriteCodes:
    def test_全コードが揃っていれば空リスト(self) -> None:
        code_row = list(REQUIRED_WRITE_CODES)
        values = [code_row]
        assert missing_write_codes(ColumnCodes(values)) == []

    def test_2つ欠けていればその2つをREQUIRED_WRITE_CODESの順で返す(self) -> None:
        missing_codes = {"PRICE_LOWEST", "CURRENCY_BUY_OTHER1"}
        code_row = [code for code in REQUIRED_WRITE_CODES if code not in missing_codes]
        values = [code_row]
        assert missing_write_codes(ColumnCodes(values)) == [
            "PRICE_LOWEST",
            "CURRENCY_BUY_OTHER1",
        ]
