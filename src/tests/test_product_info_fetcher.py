import pytest

from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin
from src.usecases.product_info_fetcher import ProductInfoFetcher

ASIN = Asin("B0CCX6ZXRV")


class FakeKeepa:
    def __init__(self, product: dict | None = None, error: Exception | None = None) -> None:
        self.product = product or {}
        self.error = error
        self.calls: list[Asin] = []

    def fetch_product(self, asin: Asin) -> dict:
        self.calls.append(asin)
        if self.error:
            raise self.error
        return self.product


class FakeSpApi:
    def __init__(self, catalog: dict | None = None, fees: dict | None = None,
                 catalog_error: Exception | None = None) -> None:
        self.catalog = catalog or {}
        self.fees = fees or {}
        self.catalog_error = catalog_error
        self.fees_calls: list[tuple[Asin, float]] = []

    def fetch_catalog_item(self, asin: Asin) -> dict:
        if self.catalog_error:
            raise self.catalog_error
        return self.catalog

    def fetch_fees_estimate(self, asin: Asin, price: float) -> dict:
        self.fees_calls.append((asin, price))
        return self.fees


FEES_OK = {
    "payload": {
        "FeesEstimateResult": {
            "Status": "Success",
            "FeesEstimate": {
                "FeeDetailList": [
                    {"FeeType": "ReferralFee", "FeeAmount": {"Amount": 74}},
                    {"FeeType": "FBAFees", "FeeAmount": {"Amount": 290}},
                ]
            },
        }
    }
}


class TestFetch:
    def test_Keepaの値を優先して返す(self) -> None:
        keepa = FakeKeepa({"title": "Keepa商品名", "imagesCSV": "71a.jpg",
                           "packageLength": 200, "packageWeight": 150,
                           "csv": {18: [1, 749]}, "monthlySold": 42})
        spapi = FakeSpApi({"attributes": {"item_name": [{"value": "SP商品名"}]}}, FEES_OK)

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert product.title == "Keepa商品名"
        assert product.monthly_sold == 42
        assert product.referral_fee == 74
        assert product.fba_fee == 290

    def test_Keepaに無い項目はSP_APIで補完する(self) -> None:
        keepa = FakeKeepa({"csv": {18: [1, 749]}})
        spapi = FakeSpApi(
            {
                "attributes": {"item_name": [{"value": "SP商品名"}],
                               "street_date": [{"value": "2019-03-11T00:00:00Z"}]},
                "dimensions": [{"type": "package",
                                "length": {"value": 20, "unit": "centimeters"},
                                "weight": {"value": 150, "unit": "grams"}}],
            },
            FEES_OK,
        )

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert product.title == "SP商品名"
        assert product.release_date == "2019-03-11"
        assert product.size.length_mm == 200
        assert product.weight_grams == 150

    def test_Keepaが失敗してもSP_APIだけで返す(self) -> None:
        keepa = FakeKeepa(error=RuntimeError("Keepa down"))
        spapi = FakeSpApi({"attributes": {"item_name": [{"value": "SP商品名"}]}}, FEES_OK)

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert product.title == "SP商品名"
        assert product.asin == ASIN

    def test_SP_APIカタログが失敗してもKeepaだけで返す(self) -> None:
        keepa = FakeKeepa({"title": "Keepa商品名", "csv": {18: [1, 749]}})
        spapi = FakeSpApi(catalog_error=RuntimeError("catalog down"), fees=FEES_OK)

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert product.title == "Keepa商品名"

    def test_カート価格が取れなければ手数料APIを呼ばない(self) -> None:
        keepa = FakeKeepa({"title": "商品", "csv": {18: [1, -1], 1: [1, -1], 0: [1, -1]}})
        spapi = FakeSpApi({}, FEES_OK)

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert spapi.fees_calls == []
        assert product.referral_fee == 0
        assert product.fba_fee == 0

    def test_手数料はカート価格を渡して見積もる(self) -> None:
        keepa = FakeKeepa({"title": "商品", "csv": {18: [1, 749]}})
        spapi = FakeSpApi({}, FEES_OK)

        ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert spapi.fees_calls == [(ASIN, 749)]

    def test_両方失敗しても空の商品情報を返す(self) -> None:
        keepa = FakeKeepa(error=RuntimeError("down"))
        spapi = FakeSpApi(catalog_error=RuntimeError("down"))

        product = ProductInfoFetcher(keepa, spapi).fetch(ASIN)

        assert product.asin == ASIN
        assert product.title == ""
