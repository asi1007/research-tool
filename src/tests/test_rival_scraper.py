from __future__ import annotations

from src.infrastructure.rival_scraper import (
    RANKING_BASE,
    absolute_ranking_url,
    organic_ranks,
    product_url,
    search_url,
)


class TestUrls:
    def test_商品ページのURL(self) -> None:
        assert product_url("B0GZVZYCQP") == "https://www.amazon.co.jp/dp/B0GZVZYCQP"

    def test_検索URLは日本語をエンコードする(self) -> None:
        assert search_url("歯ブラシ置き").startswith("https://www.amazon.co.jp/s?k=%E6%AD%AF")

    def test_検索URLは空白も落とさずエンコードする(self) -> None:
        assert "%20" in search_url("傘 目印") or "+" in search_url("傘 目印")


class TestAbsoluteRankingUrl:
    def test_相対パスにドメインを足す(self) -> None:
        assert absolute_ranking_url("/gp/bestsellers/kitchen/334646011") == (
            "https://www.amazon.co.jp/gp/bestsellers/kitchen/334646011"
        )

    def test_refより後ろは落とす(self) -> None:
        assert absolute_ranking_url("/gp/bestsellers/kitchen/2574218051/ref=pd_zg_hrsr") == (
            "https://www.amazon.co.jp/gp/bestsellers/kitchen/2574218051"
        )

    def test_絶対URLはそのまま(self) -> None:
        url = f"{RANKING_BASE}/gp/bestsellers/kitchen/1"

        assert absolute_ranking_url(url) == url

    def test_見つからなければNone(self) -> None:
        assert absolute_ranking_url("") is None
        assert absolute_ranking_url(None) is None


class TestOrganicRanks:
    def test_スポンサー枠を除いて順位を数える(self) -> None:
        cards = [
            ("B000000001", True, "広告A"),
            ("B000000002", False, "商品B"),
            ("B000000003", True, "広告C"),
            ("B000000004", False, "商品D"),
        ]

        assert organic_ranks(cards) == [
            {"rank": 1, "asin": "B000000002", "title": "商品B"},
            {"rank": 2, "asin": "B000000004", "title": "商品D"},
        ]

    def test_同じASINが二度出たら最初だけ残す(self) -> None:
        cards = [
            ("B000000001", False, "A"),
            ("B000000001", False, "A"),
            ("B000000002", False, "B"),
        ]

        assert [c["rank"] for c in organic_ranks(cards)] == [1, 2]
        assert [c["asin"] for c in organic_ranks(cards)] == ["B000000001", "B000000002"]

    def test_ASINが空のカードは飛ばす(self) -> None:
        cards = [("", False, ""), ("B000000001", False, "A")]

        assert organic_ranks(cards) == [{"rank": 1, "asin": "B000000001", "title": "A"}]

    def test_件数の上限で切る(self) -> None:
        cards = [(f"B00000000{i}", False, f"商品{i}") for i in range(1, 6)]

        assert len(organic_ranks(cards, limit=3)) == 3
