import pytest

from src.infrastructure.column_mapper import ColumnMapper


HEADERS_RESEARCH = [
    "", "", "ASIN", "GTIN", "UPC", "画像URL", "商品名", "商品名(BUY)", "金額", "数量",
    "発売日", "備考", "検索ワード", "検索数", "", "", "", "", "", "", "", "Keepaグラフ",
    "1ヶ月", "3ヶ月平均", "広告単価", "出品からの年げつ", "カート価格", "販売数/FBA数",
    "サイズ（長さ）", "サイズ(幅)", " サイズ(高さ)", "重量", "", "", "", "国際送料", "", "",
    "販売手数料", "配送代行手数料（FBA手数料）",
]

HEADERS_COMMON = [
    "", "", "ASIN", "GTIN", "UPC", "商品画像", "商品名", "商品名(BUY)", "数量", "備考",
    "検索ワード", "検索数", "", "", "", "", "", "", "", "Keepaグラフ", "1ヶ月", "3ヶ月平均",
    "", "", "", "", "カート価格", "販売数/FBA数", "", "", "", "", "国際送料", "", "",
    "販売手数料", "FBA手数料+成約料",
]


class TestColumnMapperResolve:
    def test_リサーチ系シートの画像列は画像URLに解決する(self) -> None:
        mapper = ColumnMapper(HEADERS_RESEARCH)
        assert mapper.column_index("image") == 5

    def test_共通レイアウトの画像列は商品画像に解決する(self) -> None:
        mapper = ColumnMapper(HEADERS_COMMON)
        assert mapper.column_index("image") == 5

    def test_FBA手数料はシートごとの別名に解決する(self) -> None:
        assert ColumnMapper(HEADERS_RESEARCH).column_index("fba_fee") == 39
        assert ColumnMapper(HEADERS_COMMON).column_index("fba_fee") == 36

    def test_存在しない項目はNoneを返す(self) -> None:
        assert ColumnMapper(HEADERS_COMMON).column_index("release_date") is None
        assert ColumnMapper(HEADERS_COMMON).column_index("weight") is None

    def test_高さ列の先頭空白を許容して解決する(self) -> None:
        assert ColumnMapper(HEADERS_RESEARCH).column_index("size_height") == 30

    def test_仕入ロット数の数量列には解決しない(self) -> None:
        mapper = ColumnMapper(HEADERS_RESEARCH)
        assert mapper.column_index("monthly_sold") == 27
        assert mapper.column_index("monthly_sold") != 9

    def test_ASIN列は3列目に解決する(self) -> None:
        assert ColumnMapper(HEADERS_RESEARCH).column_index("asin") == 2
        assert ColumnMapper(HEADERS_COMMON).column_index("asin") == 2

    def test_書き込み可能な項目だけを列挙する(self) -> None:
        writable = ColumnMapper(HEADERS_COMMON).writable_fields()

        assert "title" in writable
        assert "image" in writable
        assert "release_date" not in writable
        assert "size_length" not in writable
