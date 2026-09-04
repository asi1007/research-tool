from __future__ import annotations

from src.usecases.formula_filler import find_template, plan_formula_updates, rewrite_row


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
