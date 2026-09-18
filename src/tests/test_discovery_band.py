import pytest

from src.domain.value_objects.discovery_band import (
    DEFAULT_DISCOVERY_SHEET,
    DiscoveryBand,
    band_for_price,
    discovery_sheets,
)
from src.domain.value_objects.discovery_criteria import DEFAULT_MAX_AGE_DAYS


class TestFromSheetName:
    def test_N円以下は1円からN円までとして読む(self) -> None:
        band = DiscoveryBand.from_sheet_name("自動調査1000円以下")

        assert (band.min_price_yen, band.max_price_yen) == (1, 1000)
        assert band.sheet == "自動調査1000円以下"

    def test_A円_B円はA円の次からB円までとして読む(self) -> None:
        band = DiscoveryBand.from_sheet_name("自動調査1000円-2000円")

        assert (band.min_price_yen, band.max_price_yen) == (1001, 2000)

    def test_N円以上は上限なしとして読む(self) -> None:
        band = DiscoveryBand.from_sheet_name("自動調査3000円以上")

        assert band.min_price_yen == 3001
        assert band.max_price_yen == DiscoveryBand.NO_UPPER_LIMIT_YEN

    def test_全角の数字とハイフンでも読める(self) -> None:
        band = DiscoveryBand.from_sheet_name("自動調査１０００円ー２０００円")

        assert (band.min_price_yen, band.max_price_yen) == (1001, 2000)

    def test_既定のタブは1000円以下(self) -> None:
        assert DEFAULT_DISCOVERY_SHEET == "自動調査1000円以下"

    def test_価格帯を読み取れないタブ名は受け付けない(self) -> None:
        with pytest.raises(ValueError, match="価格帯"):
            DiscoveryBand.from_sheet_name("候補")

    def test_下限が上限以上になるタブ名は受け付けない(self) -> None:
        with pytest.raises(ValueError, match="価格"):
            DiscoveryBand.from_sheet_name("自動調査2000円-1000円")

    def test_タブ名から抽出条件を組み立てる(self) -> None:
        criteria = DiscoveryBand.from_sheet_name("自動調査1000円-2000円").criteria()

        assert (criteria.min_price_yen, criteria.max_price_yen) == (1001, 2000)


class TestDiscoverySheets:
    def test_自動調査で始まり価格帯を読めるタブだけを拾う(self) -> None:
        titles = [
            "リサーチ700円以下",
            "自動調査1000円以下",
            "自動調査1000円-2000円",
            "自動調査",
            "候補外",
        ]

        assert discovery_sheets(titles) == ["自動調査1000円以下", "自動調査1000円-2000円"]

    def test_価格の安い順に並べる(self) -> None:
        titles = ["自動調査1000円-2000円", "自動調査1000円以下"]

        assert discovery_sheets(titles) == ["自動調査1000円以下", "自動調査1000円-2000円"]


class TestCriteriaAge:
    def test_既定の出品からの経過は条件の既定値(self) -> None:
        criteria = DiscoveryBand.from_sheet_name("自動調査500円以下").criteria()

        assert criteria.max_age_days == DEFAULT_MAX_AGE_DAYS

    def test_出品からの経過を指定できる(self) -> None:
        band = DiscoveryBand.from_sheet_name("自動調査500円以下")

        assert band.criteria(max_age_days=1095).max_age_days == 1095
        assert band.criteria(max_age_days=None).max_age_days is None


class Test価格から帯を選ぶ:
    """手で ASIN を積むとき、価格に合う自動調査タブを決める。

    タブ名が唯一の正本。コード側に価格帯の表を持つと、タブを足したときにずれる。
    """

    SHEETS = [
        "リリース",
        "自動調査500円以下",
        "自動調査500円-700円",
        "自動調査700円-1000円",
        "自動調査1000円-2000円",
        "自動調査2000円以上",
        "idea",
    ]

    def test_帯の中の価格はその帯を返す(self) -> None:
        assert band_for_price(self.SHEETS, 498).sheet == "自動調査500円以下"
        assert band_for_price(self.SHEETS, 999).sheet == "自動調査700円-1000円"
        assert band_for_price(self.SHEETS, 1500).sheet == "自動調査1000円-2000円"

    def test_境界はその帯の上限側に入る(self) -> None:
        assert band_for_price(self.SHEETS, 500).sheet == "自動調査500円以下"
        assert band_for_price(self.SHEETS, 501).sheet == "自動調査500円-700円"
        assert band_for_price(self.SHEETS, 1000).sheet == "自動調査700円-1000円"
        assert band_for_price(self.SHEETS, 1001).sheet == "自動調査1000円-2000円"

    def test_上限なしの帯は高い価格を受ける(self) -> None:
        assert band_for_price(self.SHEETS, 9800).sheet == "自動調査2000円以上"

    def test_価格帯を読めないタブは無視する(self) -> None:
        assert band_for_price(["リリース", "idea"], 498) is None

    def test_どの帯にも入らなければNone(self) -> None:
        assert band_for_price(["自動調査500円以下"], 900) is None

    def test_価格が0以下なら落とす(self) -> None:
        with pytest.raises(ValueError):
            band_for_price(self.SHEETS, 0)
