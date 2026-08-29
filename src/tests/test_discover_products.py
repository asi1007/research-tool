from datetime import date

from src.domain.value_objects.asin import Asin
from src.usecases.discover_products import known_asins, plan_append, select_new_asins

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN"]
HEADER_2 = ["", "", "ASIN", "GTIN"]
HEADER_3 = ["0", "1", "", "JAN/EAN"]


def _sheet(asin_cells: list[str]) -> list[list]:
    return [CODE_ROW, HEADER_2, HEADER_3] + [["", "", cell, ""] for cell in asin_cells]


class TestKnownAsins:
    def test_素のASINを拾う(self) -> None:
        assert known_asins({"候補": _sheet(["B000000001"])}) == {"B000000001"}

    def test_商品URLも同じASINとして扱う(self) -> None:
        values = _sheet(["https://www.amazon.co.jp/dp/B000000002/ref=sr_1_3?th=1"])
        assert known_asins({"優先": values}) == {"B000000002"}

    def test_複数タブを合算する(self) -> None:
        sheets = {"候補": _sheet(["B000000001"]), "候補外": _sheet(["B000000003"])}
        assert known_asins(sheets) == {"B000000001", "B000000003"}

    def test_ASIN列コードが無いタブは無視する(self) -> None:
        values = [["んh", "MEMO"], ["", ""], ["", ""], ["", "B000000009"]]
        assert known_asins({"プロンプト": values}) == set()

    def test_解釈できないセルは無視する(self) -> None:
        assert known_asins({"候補": _sheet(["", "https://amzn.to/xxxx", "-"])}) == set()


class TestSelectNewAsins:
    def test_既知を除いた順序を保つ(self) -> None:
        found = [Asin("B000000001"), Asin("B000000002"), Asin("B000000003")]

        assert [str(a) for a in select_new_asins(found, {"B000000002"})] == [
            "B000000001",
            "B000000003",
        ]

    def test_同じASINが2回出ても1回にする(self) -> None:
        found = [Asin("B000000001"), Asin("B000000001")]
        assert [str(a) for a in select_new_asins(found, set())] == ["B000000001"]

    def test_上限で切る(self) -> None:
        found = [Asin("B000000001"), Asin("B000000002")]
        assert [str(a) for a in select_new_asins(found, set(), limit=1)] == ["B000000001"]


APPEND_CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL",
                   "TITLE_BUY", "NOTE_BUY_OTHER8", "NOTE_BUY_OTHER7", "", "NOTE_BUY_OTHER2"]
DISCOVERED_ON = date(2026, 8, 29)


def _append_sheet(existing: list[str]) -> list[list]:
    filler = ["", "", "", "", "", "", "", "", "", ""]
    header = [APPEND_CODE_ROW, ["", "", "ASIN"] + filler, ["0", "1", ""] + filler]
    return header + [["", "", cell] + filler for cell in existing]


class TestPlanAppend:
    def test_空行にASINと備考を書く(self) -> None:
        plan = plan_append(_append_sheet(["B000000001", "", ""]), [Asin("B000000009")], DISCOVERED_ON)

        assert plan.updates == {5: {2: "B000000009", 11: "自動調査2026-08-29"}}
        assert plan.rows_to_add == 0

    def test_空行を上から順に使う(self) -> None:
        asins = [Asin("B000000009"), Asin("B000000008")]

        plan = plan_append(_append_sheet(["B000000001", "", ""]), asins, DISCOVERED_ON)

        assert sorted(plan.updates) == [5, 6]
        assert plan.updates[6][2] == "B000000008"

    def test_空行が足りなければ行を足す(self) -> None:
        asins = [Asin("B000000009"), Asin("B000000008")]

        plan = plan_append(_append_sheet(["B000000001"]), asins, DISCOVERED_ON)

        assert sorted(plan.updates) == [5, 6]
        assert plan.rows_to_add == 2

    def test_列は列コードで引く(self) -> None:
        moved = [["んh", "ASIN_SELL", "NOTE_BUY_OTHER2"], ["", "ASIN", "備考"], ["0", "", ""], ["", "", ""]]

        plan = plan_append(moved, [Asin("B000000009")], DISCOVERED_ON)

        assert plan.updates == {4: {1: "B000000009", 2: "自動調査2026-08-29"}}

    def test_ASINが無ければ何も書かない(self) -> None:
        plan = plan_append(_append_sheet(["", ""]), [], DISCOVERED_ON)

        assert plan.updates == {}
        assert plan.rows_to_add == 0
