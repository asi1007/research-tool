from src.domain.value_objects.seasonal_verdicts import SeasonalVerdicts
from src.usecases.seasonal import (
    SEASONAL_SHEET,
    SeasonalCandidate,
    build_judge_prompt,
    is_seasonal_title,
    parse_judge_response,
    rows_to_move,
    seasonal_candidates,
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


class TestSeasonalCandidates:
    def test_キーワードに当たる行を候補にする(self) -> None:
        values = [
            CODE_ROW,
            LABEL_ROW,
            UNIT_ROW,
            _row("B000000001", "車用ベビーミラー"),
            _row("B000000002", "日傘 uvカット 折り畳み"),
        ]

        assert seasonal_candidates(values) == [
            SeasonalCandidate(row_number=5, asin="B000000002", title="日傘 uvカット 折り畳み")
        ]

    def test_ASINが無い行は候補にしない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("", "日傘 uvカット")]

        assert seasonal_candidates(values) == []

    def test_URLのASINは素のASINにする(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("https://www.amazon.co.jp/dp/B000000003", "日傘")]

        assert seasonal_candidates(values)[0].asin == "B000000003"

    def test_移送先は季節商品タブ(self) -> None:
        assert SEASONAL_SHEET == "季節商品"


class TestRowsToMove:
    def test_季節商品と判定された行だけを移す(self) -> None:
        # キーワードは候補を絞るだけ。「ファンブレードの掃除用」のように説明に反応するので判定には使わない
        verdicts = SeasonalVerdicts()
        verdicts.record_claude("B000000001", True)
        verdicts.record_claude("B000000002", False)
        candidates = [
            SeasonalCandidate(4, "B000000001", "ハンディファン"),
            SeasonalCandidate(5, "B000000002", "ホコリ取りスポンジ ファンブレード用"),
            SeasonalCandidate(6, "B000000003", "日傘"),
        ]

        assert rows_to_move(candidates, verdicts) == [4]


class TestJudgePrompt:
    def test_商品名を番号付きで並べる(self) -> None:
        prompt = build_judge_prompt(["日傘 uvカット", "洗濯ネット\n毛布用"])

        assert "0: 日傘 uvカット" in prompt
        assert "1: 洗濯ネット 毛布用" in prompt

    def test_用途の説明に季節の語があるだけの商品は季節商品にしないよう指示する(self) -> None:
        prompt = build_judge_prompt(["x"])

        assert "用途" in prompt
        assert '"seasonal"' in prompt


class TestParseJudgeResponse:
    def test_番号ごとの判定を返す(self) -> None:
        result = parse_judge_response('[{"index": 0, "seasonal": true}, {"index": 1, "seasonal": false}]', 2)

        assert result.error is None
        assert result.verdicts == {0: True, 1: False}

    def test_コードフェンスを外す(self) -> None:
        result = parse_judge_response('```json\n[{"index": 0, "seasonal": false}]\n```', 1)

        assert result.verdicts == {0: False}

    def test_件数が合わなければ全部捨てる(self) -> None:
        result = parse_judge_response('[{"index": 0, "seasonal": true}]', 2)

        assert result.error is not None
        assert result.verdicts == {}

    def test_真偽値でなければ全部捨てる(self) -> None:
        result = parse_judge_response('[{"index": 0, "seasonal": "true"}]', 1)

        assert result.error is not None

    def test_JSONでなければ全部捨てる(self) -> None:
        assert parse_judge_response("はい", 1).error is not None
