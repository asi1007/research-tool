from src.domain.entities.product_info import ProductInfo
from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin
from src.infrastructure.column_mapper import ColumnMapper
from src.usecases.row_update_planner import RowUpdatePlanner

HEADERS = [
    "", "", "ASIN", "GTIN", "UPC", "画像URL", "商品名", "商品名(BUY)", "金額", "数量",
    "発売日", "備考", "検索ワード", "検索数", "", "", "", "", "", "", "", "Keepaグラフ",
    "1ヶ月", "3ヶ月平均", "広告単価", "出品からの年げつ", "カート価格", "販売数/FBA数",
    "サイズ（長さ）", "サイズ(幅)", " サイズ(高さ)", "重量", "", "", "", "国際送料", "", "",
    "販売手数料", "配送代行手数料（FBA手数料）",
]

PRODUCT = ProductInfo(
    asin=Asin("B0CCX6ZXRV"),
    title="テスト商品",
    image_url="71abc.jpg",
    release_date="2023-01-27",
    size=ProductSize(200, 100, 30),
    weight_grams=150,
    referral_fee=74,
    fba_fee=290,
    buy_box_price=749,
    monthly_sold=42,
)


def _planner(overwrite: bool = False) -> RowUpdatePlanner:
    return RowUpdatePlanner(ColumnMapper(HEADERS), overwrite=overwrite)


class TestNeedsFetch:
    def test_書き込み対象が全て空なら取得が必要(self) -> None:
        assert _planner().needs_fetch([""] * len(HEADERS)) is True

    def test_一部が空なら取得が必要(self) -> None:
        row = [""] * len(HEADERS)
        row[6] = "既に入っている商品名"
        assert _planner().needs_fetch(row) is True

    def test_書き込み対象が全て埋まっていれば取得不要(self) -> None:
        row = [""] * len(HEADERS)
        for index in (5, 6, 10, 26, 27, 28, 29, 30, 31, 35, 38, 39):
            row[index] = "値"
        assert _planner().needs_fetch(row) is False

    def test_上書きモードでは常に取得が必要(self) -> None:
        row = [""] * len(HEADERS)
        for index in (5, 6, 10, 26, 27, 28, 29, 30, 31, 35, 38, 39):
            row[index] = "値"
        assert _planner(overwrite=True).needs_fetch(row) is True

    def test_行が短くても空欄として扱う(self) -> None:
        assert _planner().needs_fetch(["", "", "B0CCX6ZXRV"]) is True


class TestPlan:
    def test_空欄だけを埋める(self) -> None:
        row = [""] * len(HEADERS)
        row[6] = "手入力した商品名"

        updates = _planner().plan(row, PRODUCT, international_shipping=18)

        assert 6 not in updates
        assert updates[5] == PRODUCT.image_formula
        assert updates[10] == "2023-01-27"
        assert updates[26] == 749
        assert updates[27] == 42
        assert updates[35] == 18
        assert updates[38] == 74
        assert updates[39] == 290

    def test_上書きモードでは既存値も置き換える(self) -> None:
        row = [""] * len(HEADERS)
        row[6] = "手入力した商品名"

        updates = _planner(overwrite=True).plan(row, PRODUCT, international_shipping=18)

        assert updates[6] == "テスト商品"

    def test_仕入ロット数の数量列には書き込まない(self) -> None:
        updates = _planner().plan([""] * len(HEADERS), PRODUCT, international_shipping=18)

        assert 9 not in updates

    def test_取得できなかった値は書き込まない(self) -> None:
        empty = ProductInfo(asin=Asin("B0CCX6ZXRV"))

        updates = _planner().plan([""] * len(HEADERS), empty, international_shipping=0)

        assert updates == {}

    def test_寸法列が無いシートでは寸法を落とす(self) -> None:
        headers_common = ["", "", "ASIN", "", "", "商品画像", "商品名", "", "", "", "", "",
                          "", "", "", "", "", "", "", "", "", "", "", "", "", "", "",
                          "販売数/FBA数", "", "", "", "", "国際送料", "", "", "販売手数料",
                          "FBA手数料+成約料"]
        planner = RowUpdatePlanner(ColumnMapper(headers_common), overwrite=False)

        updates = planner.plan([""] * len(headers_common), PRODUCT, international_shipping=18)

        assert updates[5] == PRODUCT.image_formula
        assert updates[32] == 18
        assert updates[36] == 290
        assert set(updates) == {5, 6, 27, 32, 35, 36}


class TestZeroValues:
    def test_カート価格が0でも書き込む(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", buy_box_price=0)

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert updates[26] == 0

    def test_月間販売数が0でも書き込む(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", monthly_sold=0)

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert updates[27] == 0

    def test_手数料が0なら書き込まない(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", referral_fee=0, fba_fee=0)

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert 38 not in updates
        assert 39 not in updates

    def test_手数料が取れていれば書き込む(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", referral_fee=74, fba_fee=290)

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert updates[38] == 74
        assert updates[39] == 290

    def test_国際送料が0でも書き込む(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品")

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert updates[35] == 0

    def test_商品名が空なら書き込まない(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="")

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert 6 not in updates

    def test_画像が空なら書き込まない(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", image_url="")

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert 5 not in updates

    def test_発売日が空なら書き込まない(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", release_date="")

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert 10 not in updates

    def test_寸法が0なら書き込まない(self) -> None:
        product = ProductInfo(asin=Asin("B0CCX6ZXRV"), title="商品", size=ProductSize(0, 0, 0))

        updates = _planner().plan([""] * len(HEADERS), product, international_shipping=0)

        assert 28 not in updates
        assert 29 not in updates
        assert 30 not in updates

    def test_何も取得できなかった商品は何も書き込まない(self) -> None:
        empty = ProductInfo(asin=Asin("B0CCX6ZXRV"))

        updates = _planner().plan([""] * len(HEADERS), empty, international_shipping=0)

        assert updates == {}
