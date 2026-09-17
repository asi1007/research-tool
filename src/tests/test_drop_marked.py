from src.usecases.drop_marked import (
    DROP_MARK,
    MARK_DESTINATIONS,
    SEASONAL_MARK,
    build_transfer_rows,
    marked_row_numbers,
    plan_transfer,
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

    def test_sの印は季節商品として拾う(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("d", "B000000001", "x"), _row("ｓ", "B000000002", "y")]

        assert marked_row_numbers(values, SEASONAL_MARK) == [5]

    def test_印ごとの移動先(self) -> None:
        assert MARK_DESTINATIONS == {"d": "候補外", "s": "季節商品"}


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


class TestPlanTransfer:
    SOURCE = [
        ["んh", "ASIN_SELL", "PRICE_SELL", "NOTE_BUY_OTHER7", "NOTE_BUY_OTHER8"],
        ["", "ASIN", "カート価格", "数量", "月間販売高"],
        ["", "", "", "", ""],
        ["", "B000000001", "900", "10", "=D4*C4"],
        ["d", "B000000002", "800", "20", "=D5*C5"],
    ]
    TARGET = [
        ["CHECK1", "NOTE_BUY_OTHER8", "ASIN_SELL", "NOTE_BUY_OTHER7", "PRICE_SELL"],
        ["", "月間販売高", "ASIN", "数量", "カート価格"],
        ["", "", "", "", ""],
        ["", "", "B000000009", "", ""],
    ]

    def test_最終行の下へ移動先の列で書く(self) -> None:
        plan = plan_transfer(self.SOURCE, self.TARGET, [5])

        assert plan == {5: {1: "=D5*E5", 2: "B000000002", 3: "20", 4: "800"}}

    def test_複数行は順に下へ積み行番号もそれぞれずらす(self) -> None:
        plan = plan_transfer(self.SOURCE, self.TARGET, [4, 5])

        assert plan[5][1] == "=D5*E5"
        assert plan[6][1] == "=D6*E6"
        assert plan[6][2] == "B000000002"

    def test_移動先に無い列を参照する数式は書かない(self) -> None:
        target = [row[:4] for row in self.TARGET]

        plan = plan_transfer(self.SOURCE, target, [5])

        assert 1 not in plan[5]

    def test_移す行が無ければ空(self) -> None:
        assert plan_transfer(self.SOURCE, self.TARGET, []) == {}
