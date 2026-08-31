from src.infrastructure.sheet_repository import plan_append_rows


class TestPlanAppendRows:
    def test_値のある最終行の次から書く(self) -> None:
        values = [["A"], ["B"], [""]]

        plan = plan_append_rows(values, [["x", "y"]])

        assert plan == {3: {0: "x", 1: "y"}}

    def test_複数行は続けて書く(self) -> None:
        values = [["A"]]

        plan = plan_append_rows(values, [["x"], ["y"]])

        assert plan == {2: {0: "x"}, 3: {0: "y"}}

    def test_空セルは書かない(self) -> None:
        values = [["A"]]

        plan = plan_append_rows(values, [["", "y", ""]])

        assert plan == {2: {1: "y"}}

    def test_末尾の空行は詰めて書く(self) -> None:
        values = [["A"], [""], ["", ""]]

        plan = plan_append_rows(values, [["x"]])

        assert plan == {2: {0: "x"}}

    def test_行が無ければ何も書かない(self) -> None:
        assert plan_append_rows([["A"]], []) == {}

    def test_値が1つも無いシートは先頭から書く(self) -> None:
        assert plan_append_rows([], [["x"]]) == {1: {0: "x"}}
