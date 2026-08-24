from __future__ import annotations

from find_supplier import REQUIRED_WRITE_CODES, is_link_lowest_blank, missing_write_codes
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


class TestIsLinkLowestBlank:
    def test_対象行のLINK_LOWESTが空なら書き込んでよい(self) -> None:
        values = [[], [], [], ["", "", ""]]
        assert is_link_lowest_blank(values, row_number=4, link_index=2) is True

    def test_対象行のLINK_LOWESTに値があれば書き込んではいけない(self) -> None:
        values = [[], [], [], ["", "", "https://detail.1688.com/offer/1.html"]]
        assert is_link_lowest_blank(values, row_number=4, link_index=2) is False

    def test_対象行のLINK_LOWESTが空白文字のみなら空とみなす(self) -> None:
        values = [[], [], [], ["", "", "  \n"]]
        assert is_link_lowest_blank(values, row_number=4, link_index=2) is True

    def test_対象行がvaluesの範囲外なら書き込んではいけない(self) -> None:
        values = [[], [], [], ["", "", ""]]
        assert is_link_lowest_blank(values, row_number=99, link_index=2) is False
