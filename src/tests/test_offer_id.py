from src.domain.value_objects.offer_id import OfferId


class TestOfferIdParse:
    def test_数字文字列をそのまま受け取る(self) -> None:
        assert OfferId.parse("620082943880") == OfferId("620082943880")

    def test_数値型も受け取る(self) -> None:
        assert OfferId.parse(620082943880) == OfferId("620082943880")

    def test_前後の空白を除去する(self) -> None:
        assert OfferId.parse("  853573456382 \n") == OfferId("853573456382")

    def test_商品URLから抽出する(self) -> None:
        url = "https://detail.1688.com/offer/956382552398.html"
        assert OfferId.parse(url) == OfferId("956382552398")

    def test_クエリ付きURLからも抽出する(self) -> None:
        url = "https://detail.1688.com/offer/674801468466.html?kj_agent_plugin=aliprice&fromkv=xyt"
        assert OfferId.parse(url) == OfferId("674801468466")

    def test_数字以外はNoneを返す(self) -> None:
        assert OfferId.parse("abc") is None

    def test_空はNoneを返す(self) -> None:
        assert OfferId.parse("") is None
        assert OfferId.parse("   ") is None
        assert OfferId.parse(None) is None


class TestOfferIdDetailUrl:
    def test_クエリを含まない商品URLを組み立てる(self) -> None:
        assert OfferId("620082943880").detail_url == "https://detail.1688.com/offer/620082943880.html"
