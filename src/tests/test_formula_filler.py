from __future__ import annotations

from src.usecases.formula_filler import (
    FORMULA_CODES,
    find_template,
    formula_columns,
    plan_formula_updates,
    rebase_formula,
    rewrite_row,
)


class TestRewriteRow:
    def test_相対参照を対象行へずらす(self) -> None:
        assert rewrite_row("=I90*O90", source_row=90, target_row=93) == "=I93*O93"

    def test_複数列にまたがる式もずらす(self) -> None:
        formula = "=N4-T4-V4-W4-Y4-Z4"

        assert rewrite_row(formula, source_row=4, target_row=12) == "=N12-T12-V12-W12-Y12-Z12"

    def test_別の行番号は触らない(self) -> None:
        assert rewrite_row("=I4*O40", source_row=4, target_row=9) == "=I9*O40"

    def test_絶対参照の行は触らない(self) -> None:
        assert rewrite_row("=I4*$O$4", source_row=4, target_row=9) == "=I9*$O$4"


class TestFindTemplate:
    def test_最初に数式のある行を雛形にする(self) -> None:
        values = [
            ["CODE"],
            ["見出し2"],
            ["見出し3"],
            ["", ""],
            ["", "=A5*2"],
            ["", "=A6*2"],
        ]

        assert find_template(values, column=1, header_rows=3) == (5, "=A5*2")

    def test_自分の行を参照していない数式は雛形にしない(self) -> None:
        # 別のタブから写した行は元の行番号を参照したままのことがある
        values = [["CODE"], ["h2"], ["h3"], ["", ""], ["", "=A40*2"], ["", "=A6*2"]]

        assert find_template(values, column=1, header_rows=3) == (6, "=A6*2")

    def test_数式が一つも無ければNone(self) -> None:
        values = [["CODE"], ["h2"], ["h3"], ["", "100"]]

        assert find_template(values, column=1, header_rows=3) is None


class TestPlanFormulaUpdates:
    def test_空欄の行だけ埋める(self) -> None:
        values = [
            ["CODE", "CODE"],
            ["", ""],
            ["ASIN", "利益"],
            ["B000000001", "=A4*2"],
            ["B000000002", ""],
            ["B000000003", ""],
        ]

        updates = plan_formula_updates(values, asin_column=0, formula_columns=[1], header_rows=3)

        assert updates == {5: {1: "=A5*2"}, 6: {1: "=A6*2"}}

    def test_ASINが無い行は埋めない(self) -> None:
        values = [
            ["CODE", "CODE"],
            ["", ""],
            ["ASIN", "利益"],
            ["B000000001", "=A4*2"],
            ["", ""],
        ]

        updates = plan_formula_updates(values, asin_column=0, formula_columns=[1], header_rows=3)

        assert updates == {}


class TestRebaseFormula:
    def test_行番号を移動先の行へずらす(self) -> None:
        assert rebase_formula("=L135*J135", 135, 7, {"L": "L", "J": "J"}) == "=L7*J7"

    def test_列を移動先の列コードの位置へ付け替える(self) -> None:
        # 候補外タブは列の並びが違う。元の列記号のままだと別の列を計算する
        assert rebase_formula("=L135*J135", 135, 7, {"L": "N", "J": "M"}) == "=N7*M7"

    def test_移動先に無い列を参照する数式は書かない(self) -> None:
        assert rebase_formula("=L135*J135", 135, 7, {"L": "N"}) is None

    def test_文字列の中は触らない(self) -> None:
        formula = '=HYPERLINK("https://www.amazon.co.jp/dp/B0DK31J42B", IMAGE("https://m.media-amazon.com/images/I/61b4yQ.jpg"))'

        assert rebase_formula(formula, 135, 7, {}) == formula

    def test_別の行を指す参照と絶対参照は触らない(self) -> None:
        assert rebase_formula("=I4*O40*$A$1", 4, 9, {"I": "J"}) == "=J9*O40*$A$1"

    def test_関数名は参照と見なさない(self) -> None:
        assert rebase_formula('=IF(T4="",NA(),K4/Y4)', 4, 9, {"T": "T", "K": "K", "Y": "Y"}) == '=IF(T9="",NA(),K9/Y9)'


class TestFormulaColumns:
    def test_利益とROIまわりの数式列を列コードで引く(self) -> None:
        values = [["んh", "ASIN_SELL", "ROI", "INVESTMENT", "NOTE_BUY_OTHER8", "RETURN", "PROFIT_RATE",
                   "PRICE_SELL", "PROFIT", "PRICE_LOWEST", "TAX", "COST"]]

        assert formula_columns(values) == [2, 3, 4, 5, 6, 8, 10, 11]

    def test_購入価格は数式列に含めない(self) -> None:
        # 購入価格は仕入先を書くときに数量倍率つきで入る（=U5*24*10）。雛形で埋めると倍率が消える
        assert "PRICE_LOWEST" not in FORMULA_CODES

    def test_無い列は飛ばす(self) -> None:
        assert formula_columns([["ASIN_SELL", "PROFIT"]]) == [1]
