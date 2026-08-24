import pytest

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId
from src.infrastructure.column_codes import ColumnCodes
from src.usecases.build_supplier_updates import build_updates

CODE_ROW = [
    "LINK_LOWEST",            # 0
    "PRICE_LOWEST",           # 1
    "LOCALPRICE_LOWEST",      # 2
    "SHIPPING_INTL",          # 3
    "LINK_BUY_OTHER1",        # 4
    "PRICE_BUY_OTHER1",       # 5
    "CURRENCY_BUY_OTHER1",    # 6
    "LOCALPRICE_BUY_OTHER1",  # 7
    "SHIPPING_INTL_OTHER1",   # 8
    "LINK_BUY_OTHER2",        # 9
    "PRICE_BUY_OTHER2",       # 10
    "CURRENCY_BUY_OTHER2",    # 11
    "LOCALPRICE_BUY_OTHER2",  # 12
    "SHIPPING_INTL_OTHER2",   # 13
]


@pytest.fixture
def codes() -> ColumnCodes:
    return ColumnCodes([CODE_ROW, [], []])


def candidate(offer: str, price: float | None) -> SupplierCandidate:
    return SupplierCandidate(
        offer_id=OfferId(offer),
        title="强力磁铁",
        company="雄尊磁铁厂",
        province="浙江",
        local_price=price,
    )


class TestBuildUpdates:
    def test_1件目は購入先に入り通貨は書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", 0.03)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert updates[2] == 0.03
        assert updates[1] == "=C5*24"

    def test_2件目は通貨CHYを書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5, [candidate("1", 0.03), candidate("853573456382", 0.05)], codes
        )
        assert updates[4] == "https://detail.1688.com/offer/853573456382.html"
        assert updates[6] == "CHY"
        assert updates[7] == 0.05
        assert updates[5] == "=H5*24"

    def test_3件目も通貨CHYを書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            9, [candidate("1", 0.01), candidate("2", 0.02), candidate("956382552398", 0.09)], codes
        )
        assert updates[9] == "https://detail.1688.com/offer/956382552398.html"
        assert updates[11] == "CHY"
        assert updates[12] == 0.09
        assert updates[10] == "=M9*24"

    def test_直送送料には書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5, [candidate("1", 0.01), candidate("2", 0.02), candidate("3", 0.03)], codes
        )
        assert 8 not in updates
        assert 13 not in updates

    def test_候補が2件なら3件目の列は触らない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("1", 0.01), candidate("2", 0.02)], codes)
        assert 9 not in updates
        assert 11 not in updates

    def test_候補が0件なら何も書かない(self, codes: ColumnCodes) -> None:
        assert build_updates(5, [], codes) == {}

    def test_価格が不明なら価格と現地価格を書かずURLだけ書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", None)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert 1 not in updates
        assert 2 not in updates

    def test_2件目の価格が不明なら通貨も書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("1", 0.01), candidate("853573456382", None)], codes)
        assert updates[4] == "https://detail.1688.com/offer/853573456382.html"
        assert 5 not in updates
        assert 6 not in updates
        assert 7 not in updates

    def test_3件目の価格が不明なら通貨も書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5, [candidate("1", 0.01), candidate("2", 0.02), candidate("956382552398", None)], codes
        )
        assert updates[9] == "https://detail.1688.com/offer/956382552398.html"
        assert 10 not in updates
        assert 11 not in updates
        assert 12 not in updates

    def test_価格が0なら価格と現地価格を書かずURLだけ書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", 0.0)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert 1 not in updates
        assert 2 not in updates

    def test_2件目の価格が0なら通貨も書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("1", 0.01), candidate("853573456382", 0.0)], codes)
        assert updates[4] == "https://detail.1688.com/offer/853573456382.html"
        assert 5 not in updates
        assert 6 not in updates
        assert 7 not in updates

    def test_価格が負なら価格と現地価格を書かずURLだけ書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", -0.01)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert 1 not in updates
        assert 2 not in updates

    def test_4件目以降は無視する(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5,
            [candidate("1", 0.01), candidate("2", 0.02), candidate("3", 0.03), candidate("4", 0.04)],
            codes,
        )
        assert len([v for v in updates.values() if str(v).startswith("https://")]) == 3
