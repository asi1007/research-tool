from src.infrastructure.image_formula import extract_image_url


class TestExtractImageUrl:
    def test_HYPERLINKとIMAGEの数式から画像URLを取り出す(self) -> None:
        cell = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
        assert extract_image_url(cell) == "https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"

    def test_IMAGEのみの数式からも取り出す(self) -> None:
        cell = '=IMAGE("https://m.media-amazon.com/images/I/71RCFDW42qL.jpg")'
        assert extract_image_url(cell) == "https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"

    def test_素のURLはそのまま返す(self) -> None:
        cell = "https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"
        assert extract_image_url(cell) == cell

    def test_空はNoneを返す(self) -> None:
        assert extract_image_url("") is None
        assert extract_image_url(None) is None

    def test_画像を含まない数式はNoneを返す(self) -> None:
        assert extract_image_url('=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", "商品")') is None

    def test_商品URLの方を誤って返さない(self) -> None:
        cell = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
        assert "amazon.co.jp" not in extract_image_url(cell)
