from src.domain.value_objects.asin import Asin
from src.usecases.discover_products import known_asins, select_new_asins

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
