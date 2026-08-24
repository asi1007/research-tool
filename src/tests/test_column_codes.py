from src.infrastructure.column_codes import ColumnCodes

VALUES = [
    ["んh", "CHECK2", "ASIN_SELL", "", "", "IMAGE", "LINK_LOWEST", "PRICE_LOWEST",
     "LOCALPRICE_LOWEST", "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "LINK_BUY_OTHER2"],
    ["", "", "ASIN", "", "", "画像URL", "購入先", "購入\n価格", "現地\n価格", "他仕入先1", "", "他仕入先2"],
    ["0", "1", "", "JAN/EAN", "UPC", "", "", "", "", "名称", "価格", "名称"],
    ["", "", "B0CCX6ZXRV"],
]


class TestColumnCodes:
    def test_コードから列番号を引く(self) -> None:
        codes = ColumnCodes(VALUES)
        assert codes.index_of("LINK_LOWEST") == 6
        assert codes.index_of("ASIN_SELL") == 2
        assert codes.index_of("IMAGE") == 5

    def test_名称が重複していても他仕入先を区別できる(self) -> None:
        codes = ColumnCodes(VALUES)
        assert codes.index_of("LINK_BUY_OTHER1") == 9
        assert codes.index_of("LINK_BUY_OTHER2") == 11

    def test_存在しないコードはNoneを返す(self) -> None:
        assert ColumnCodes(VALUES).index_of("CURRENCY_BUY_OTHER9") is None

    def test_前後の空白と改行を無視して一致させる(self) -> None:
        codes = ColumnCodes([[" LINK_LOWEST\n"], [""], [""]])
        assert codes.index_of("LINK_LOWEST") == 0

    def test_空のシートでもNoneを返す(self) -> None:
        assert ColumnCodes([]).index_of("LINK_LOWEST") is None
