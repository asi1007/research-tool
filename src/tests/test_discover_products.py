from datetime import date

import pytest

from src.domain.entities.product_info import ProductInfo
from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
from src.usecases.discover_products import (
    known_asins,
    plan_append,
    select_by_revenue,
    select_new_asins,
)

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

    def test_行の長さがASIN列に届かない場合は無視する(self) -> None:
        values = [CODE_ROW, HEADER_2, HEADER_3, ["", ""]]
        assert known_asins({"候補": values}) == set()


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

    def test_上限0件なら何も返さない(self) -> None:
        found = [Asin("B000000001"), Asin("B000000002")]
        assert select_new_asins(found, set(), limit=0) == []

    def test_上限が負の数でも何も返さない(self) -> None:
        found = [Asin("B000000001")]
        assert select_new_asins(found, set(), limit=-1) == []


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

    def test_空行が一部だけ足りる場合は空行と新規行を混在させる(self) -> None:
        asins = [Asin("B000000009"), Asin("B000000008")]

        plan = plan_append(_append_sheet(["B000000001", ""]), asins, DISCOVERED_ON)

        assert sorted(plan.updates) == [5, 6]
        assert plan.updates[5][2] == "B000000009"
        assert plan.updates[6][2] == "B000000008"
        assert plan.rows_to_add == 1

    def test_列コードが欠けていると例外(self) -> None:
        values = [["んh", "OTHER_CODE"], ["", ""], ["", ""], ["", ""]]

        with pytest.raises(ValueError, match="ASIN_SELL"):
            plan_append(values, [Asin("B000000009")], DISCOVERED_ON)

    def test_3行未満のシートでもヘッダー行には書き込まない(self) -> None:
        values = [
            ["んh", "CHECK2", "ASIN_SELL", "NOTE_BUY_OTHER2"],
            ["", "", "ASIN", "備考"],
        ]

        plan = plan_append(values, [Asin("B000000009")], DISCOVERED_ON)

        assert plan.updates == {4: {2: "B000000009", 3: "自動調査2026-08-29"}}
        assert plan.rows_to_add == 1


class TestSelectByRevenue:
    def _product(self, asin: str, price: float, sold: int) -> ProductInfo:
        return ProductInfo(asin=Asin(asin), buy_box_price=price, monthly_sold=sold)

    def test_月商が基準に満たない商品を落とす(self) -> None:
        criteria = DiscoveryCriteria(min_price_yen=1001, max_price_yen=2000)
        products = [
            self._product("B000000001", 1500, 400),  # 60万
            self._product("B000000002", 1200, 300),  # 36万
            self._product("B000000003", 2000, 250),  # 50万ちょうど
        ]

        selected = select_by_revenue(products, criteria)

        assert [str(asin) for asin in selected] == ["B000000001", "B000000003"]

    def test_価格が取れない商品は落とす(self) -> None:
        criteria = DiscoveryCriteria()
        products = [self._product("B000000004", 0, 100_000)]

        assert select_by_revenue(products, criteria) == []


class TestSelectByCategory:
    def _product(self, asin: str, root_category: int) -> ProductInfo:
        return ProductInfo(
            asin=Asin(asin),
            buy_box_price=1000,
            monthly_sold=1000,
            root_category=root_category,
        )

    def test_除外カテゴリの商品を落とす(self) -> None:
        criteria = DiscoveryCriteria()
        products = [
            self._product("B000000001", 3828871),   # ホーム＆キッチン
            self._product("B000000002", 57239051),  # 食品・飲料・お酒
        ]

        selected = select_by_revenue(products, criteria)

        assert [str(asin) for asin in selected] == ["B000000001"]

    def test_categoryTreeが空でもrootCategoryで弾ける(self) -> None:
        # Keepa の categories_exclude は categoryTree を見るため、
        # ツリーが空の商品はクエリでは除外できない（2026-09-03 に食品が1件通った）
        criteria = DiscoveryCriteria()

        assert select_by_revenue([self._product("B000000003", 465392)], criteria) == []

    def test_カテゴリ不明の商品は落とさない(self) -> None:
        criteria = DiscoveryCriteria()

        assert len(select_by_revenue([self._product("B000000004", 0)], criteria)) == 1


class TestExcludedBrands:
    def _product(self, asin: str, title: str) -> ProductInfo:
        return ProductInfo(
            asin=Asin(asin), title=title, buy_box_price=1000, monthly_sold=1000
        )

    def test_タカラトミーは対象外(self) -> None:
        criteria = DiscoveryCriteria()
        products = [
            self._product("B000000001", "タカラトミー(TAKARA TOMY) トミカ 覆面パトロールカー"),
            self._product("B000000002", "車用 ベビーミラー 後部座席"),
        ]

        selected = select_by_revenue(products, criteria)

        assert [str(asin) for asin in selected] == ["B000000002"]

    def test_英字表記でも弾く(self) -> None:
        criteria = DiscoveryCriteria()

        assert select_by_revenue([self._product("B000000003", "TAKARA TOMY Tomica")], criteria) == []

    def test_商品名が空でも落ちない(self) -> None:
        criteria = DiscoveryCriteria()

        assert len(select_by_revenue([self._product("B000000004", "")], criteria)) == 1
