from src.usecases.drop_marked import (
    DROP_MARK,
    build_transfer_rows,
    marked_row_numbers,
)

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY"]
LABEL_ROW = ["", "", "ASIN", "GTIN", "", "画像URL", "商品名", "商品名(BUY)"]
UNIT_ROW = ["0", "1", "", "", "", "", "", ""]

TARGET_CODE_ROW = ["CHECK1", "CHECK2", "ASIN_SELL", "TITLE_SELL"]


def _row(mark: str, asin: str, title: str) -> list[str]:
    return [mark, "", asin, "", "", "", title, ""]


class TestMarkedRowNumbers:
    def test_A列がdの行を拾う(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("", "B000000001", "残す"), _row("d", "B000000002", "消す")]

        assert marked_row_numbers(values) == [5]

    def test_大文字や全角のDも同じ扱いにする(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("D", "B000000001", "x"), _row("ｄ", "B000000002", "y")]

        assert marked_row_numbers(values) == [4, 5]

    def test_他の印は拾わない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("NEW", "B000000001", "x")]

        assert marked_row_numbers(values) == []

    def test_ASINが無い行は拾わない(self) -> None:
        # 消しても再登場を防げないので、印だけの空行は対象にしない
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("d", "", "x")]

        assert marked_row_numbers(values) == []

    def test_印は既定でdだけ(self) -> None:
        assert DROP_MARK == "d"


class TestBuildTransferRows:
    def test_共通する列コードの値だけを移す(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("d", "B000000002", "消す商品")]
        target_values = [TARGET_CODE_ROW, ["", "", "ASIN", "商品名"], ["", "", "", ""]]

        rows = build_transfer_rows(values, target_values, [4])

        assert rows == [["", "", "B000000002", "消す商品"]]

    def test_移す行が無ければ空(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW]
        target_values = [TARGET_CODE_ROW]

        assert build_transfer_rows(values, target_values, []) == []
