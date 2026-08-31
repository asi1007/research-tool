from src.usecases.fill_keywords import (
    KEYWORD_COUNT,
    KeywordSuggestion,
    build_keyword_updates,
    parse_recommendations,
)

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY",
            "NOTE_BUY_OTHER8", "NOTE_BUY_OTHER7", "", "NOTE_BUY_OTHER2",
            "NOTE_BUY_OTHER3", "NOTE_BUY_OTHER4", "IS_LARGE", "", "", "", "", "", "", "", "", "",
            "NOTE_BUY_OTHER5"]
LABEL_ROW = [""] * 25
UNIT_ROW = [""] * 25


def _row(asin: str, keyword: str = "", bid: str = "") -> list[str]:
    row = [""] * len(CODE_ROW)
    row[2] = asin
    row[12] = keyword
    row[24] = bid
    return row


def _response(pairs: list[tuple[str, int, int]]) -> dict:
    return {
        "keywordTargetList": [
            {
                "keyword": keyword,
                "bidInfo": [
                    {"matchType": "EXACT", "rank": rank, "bid": bid},
                    {"matchType": "BROAD", "rank": rank, "bid": bid + 1000},
                ],
            }
            for keyword, rank, bid in pairs
        ]
    }


class TestParseRecommendations:
    def test_入札額は100分の1にして円に直す(self) -> None:
        suggestions = parse_recommendations(_response([("強力ライト", 1, 9700)]))

        assert suggestions == [KeywordSuggestion(keyword="強力ライト", bid_yen=97)]

    def test_完全一致の入札額を使う(self) -> None:
        response = {
            "keywordTargetList": [
                {
                    "keyword": "キャスター 固定",
                    "bidInfo": [
                        {"matchType": "BROAD", "rank": 1, "bid": 8000},
                        {"matchType": "EXACT", "rank": 1, "bid": 5100},
                    ],
                }
            ]
        }

        assert parse_recommendations(response)[0].bid_yen == 51

    def test_上位から既定の件数だけ取る(self) -> None:
        pairs = [(f"キーワード{index}", index, 1000 * index) for index in range(1, 10)]

        assert len(parse_recommendations(_response(pairs))) == KEYWORD_COUNT

    def test_完全一致が無いキーワードは落とす(self) -> None:
        response = {
            "keywordTargetList": [
                {"keyword": "x", "bidInfo": [{"matchType": "BROAD", "rank": 1, "bid": 8000}]}
            ]
        }

        assert parse_recommendations(response) == []

    def test_候補が無ければ空(self) -> None:
        assert parse_recommendations({"keywordTargetList": []}) == []


class TestBuildKeywordUpdates:
    def test_検索ワードと広告単価を改行区切りで書く(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001")]
        suggestions = [
            KeywordSuggestion("強力ライト", 97),
            KeywordSuggestion("懐中電灯 強力", 113),
        ]

        updates = build_keyword_updates(values, "B000000001", suggestions)

        assert updates == {4: {12: "強力ライト\n懐中電灯 強力", 24: "97\n113"}}

    def test_既に値がある行は上書きしない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001", keyword="手入力")]

        updates = build_keyword_updates(values, "B000000001", [KeywordSuggestion("x", 10)])

        assert updates == {}

    def test_ASINが見つからなければ書かない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001")]

        assert build_keyword_updates(values, "B000000009", [KeywordSuggestion("x", 10)]) == {}

    def test_候補が無ければ書かない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001")]

        assert build_keyword_updates(values, "B000000001", []) == {}
