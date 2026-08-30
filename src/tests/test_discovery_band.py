import pytest

from src.domain.value_objects.discovery_band import (
    DEFAULT_DISCOVERY_SHEET,
    DiscoveryBand,
    discovery_sheets,
)


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
