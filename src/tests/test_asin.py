import pytest

from src.domain.value_objects.asin import Asin


class TestAsinParse:
    def test_素のASINをそのまま受け取る(self) -> None:
        assert Asin.parse("B0CCX6ZXRV") == Asin("B0CCX6ZXRV")

    def test_前後の空白を除去する(self) -> None:
        assert Asin.parse("  B0CQ245KMT \n") == Asin("B0CQ245KMT")

    def test_小文字は大文字に正規化する(self) -> None:
        assert Asin.parse("b0fs1xtj16") == Asin("B0FS1XTJ16")

    def test_全角英数を半角に正規化する(self) -> None:
        assert Asin.parse("Ｂ０ＣＣＸ６ＺＸＲＶ") == Asin("B0CCX6ZXRV")

    def test_商品URLからdpのASINを抽出する(self) -> None:
        url = "https://www.amazon.co.jp/TARATI-%E8%B6%85/dp/B0H455Y954/ref=sr_1_18?dib=xxx&th=1"
        assert Asin.parse(url) == Asin("B0H455Y954")

    def test_gp_productのURLからも抽出する(self) -> None:
        url = "https://www.amazon.co.jp/gp/product/B08N5WRWNW?psc=1"
        assert Asin.parse(url) == Asin("B08N5WRWNW")

    def test_dpの直後にクエリが続くURLからも抽出する(self) -> None:
        assert Asin.parse("https://www.amazon.co.jp/dp/B07XJ8C8F5?th=1") == Asin("B07XJ8C8F5")

    def test_短縮URLのamzn_toは抽出できないのでNoneを返す(self) -> None:
        assert Asin.parse("https://amzn.to/3xYzAbC") is None

    def test_検索ワードはNoneを返す(self) -> None:
        assert Asin.parse("掃除グッズ　水垢とか") is None

    def test_URL断片はNoneを返す(self) -> None:
        assert Asin.parse("1.sym.f293be60-50b7-49bc-95e8-931faf86ed1e&pf_rd_p=xxx") is None

    def test_空文字はNoneを返す(self) -> None:
        assert Asin.parse("") is None
        assert Asin.parse("   ") is None

    def test_桁数が足りない文字列はNoneを返す(self) -> None:
        assert Asin.parse("B0CCX6ZX") is None

    def test_桁数が多い文字列はNoneを返す(self) -> None:
        assert Asin.parse("B0CCX6ZXRVXX") is None

    def test_ハイフンを含む10文字はNoneを返す(self) -> None:
        assert Asin.parse("B0CC-X6ZXR") is None


class TestAsinAmazonUrl:
    def test_日本のAmazon商品URLを組み立てる(self) -> None:
        assert Asin("B0CCX6ZXRV").amazon_url == "https://www.amazon.co.jp/dp/B0CCX6ZXRV"
