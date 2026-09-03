from src.usecases.seasonal import (
    SEASONAL_SHEET,
    is_seasonal_title,
    seasonal_row_numbers,
)

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY"]
LABEL_ROW = ["", "", "ASIN", "", "", "", "商品名", "商品名(BUY)"]
UNIT_ROW = ["", "", "", "", "", "", "", ""]


def _row(asin: str, title: str) -> list[str]:
    row = [""] * len(CODE_ROW)
    row[2] = asin
    row[6] = title
    return row


class TestIsSeasonalTitle:
    def test_日傘は夏物(self) -> None:
        assert is_seasonal_title("vivisan 日傘 uvカット 遮熱 ワンタッチ 自動開閉 折り畳み日傘") is True

    def test_扇風機は夏物(self) -> None:
        assert is_seasonal_title("【2026夏新登場】クリップ扇風機 卓上扇風機 小型 Type-C充電式") is True

    def test_冷却プレートのハンディファンは夏物(self) -> None:
        assert is_seasonal_title("ハンディファン 冷却プレート付き 携帯扇風機 冷感 手持ち扇風機") is True

    def test_氷嚢は夏物(self) -> None:
        assert is_seasonal_title("氷嚢 魔法瓶構造 氷のう 熱中症対策 グッズ 暑さ対策") is True

    def test_水着は夏物(self) -> None:
        assert is_seasonal_title("レディース 水着 体型カバー タンキニ") is True

    def test_スイムゴーグルは夏物(self) -> None:
        assert is_seasonal_title("水中メガネ スイミングゴーグル 水泳 曇り止め") is True

    def test_電熱ベストは冬物として季節商品にする(self) -> None:
        assert is_seasonal_title("電熱ベスト ヒーターベスト DC7.4V 30000mAh") is True

    def test_通年の商品は季節ではない(self) -> None:
        assert is_seasonal_title("車用 ベビーミラー 後部座席 角度調整 ルームミラー") is False
        assert is_seasonal_title("デジタルスケール クッキングスケール 電子天秤 0.1g/3.0kg") is False

    def test_扇風機に似た語でも誤検出しない(self) -> None:
        # 「冷蔵」「冷凍」は季節ではない
        assert is_seasonal_title("冷蔵庫 収納ケース 冷凍保存 小分けパック") is False

    def test_空の商品名は季節ではない(self) -> None:
        assert is_seasonal_title("") is False


class TestSeasonalRowNumbers:
    def test_夏物の行番号を返す(self) -> None:
        values = [
            CODE_ROW,
            LABEL_ROW,
            UNIT_ROW,
            _row("B000000001", "車用ベビーミラー"),
            _row("B000000002", "日傘 uvカット 折り畳み"),
        ]

        assert seasonal_row_numbers(values) == [5]

    def test_ASINが無い行は対象にしない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("", "日傘 uvカット")]

        assert seasonal_row_numbers(values) == []

    def test_移送先は季節商品タブ(self) -> None:
        assert SEASONAL_SHEET == "季節商品"
