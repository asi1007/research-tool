from src.usecases.search_rank import (
    RANK_CODE,
    build_rank_updates,
    build_rank_index,
    last_sunday,
    lookup_ranks,
)
from datetime import date

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL"] + [""] * 9 + ["NOTE_BUY_OTHER3"] + [""] * 58 + ["SEARCH_RANK"]
LABEL_ROW = [""] * len(CODE_ROW)
UNIT_ROW = [""] * len(CODE_ROW)
RANK_INDEX = len(CODE_ROW) - 1
KEYWORD_INDEX = 12


def _row(asin: str, keywords: str = "", rank: str = "") -> list[str]:
    row = [""] * len(CODE_ROW)
    row[2] = asin
    row[KEYWORD_INDEX] = keywords
    row[RANK_INDEX] = rank
    return row


class TestLastSunday:
    def test_レポートの開始日は直近の日曜にそろえる(self) -> None:
        # 2026-08-31 は月曜。その前の完全な週は 8/16(日)〜8/22(土)
        assert last_sunday(date(2026, 8, 31), weeks_ago=2) == date(2026, 8, 16)

    def test_日曜そのものも日曜として扱う(self) -> None:
        assert last_sunday(date(2026, 8, 30), weeks_ago=1) == date(2026, 8, 23)


class TestBuildRankIndex:
    def test_同じキーワードの重複はまとめる(self) -> None:
        report = {
            "dataByDepartmentAndSearchTerm": [
                {"searchTerm": "懐中電灯", "searchFrequencyRank": 694},
                {"searchTerm": "懐中電灯", "searchFrequencyRank": 694},
                {"searchTerm": "懐中電灯 強力", "searchFrequencyRank": 6876},
            ]
        }

        assert build_rank_index(report) == {"懐中電灯": 694, "懐中電灯 強力": 6876}

    def test_順位が無い行は落とす(self) -> None:
        report = {"dataByDepartmentAndSearchTerm": [{"searchTerm": "x", "searchFrequencyRank": None}]}

        assert build_rank_index(report) == {}

    def test_大文字と全角は畳んで引けるようにする(self) -> None:
        report = {"dataByDepartmentAndSearchTerm": [{"searchTerm": "ＬＥＤ Light", "searchFrequencyRank": 5}]}

        assert build_rank_index(report) == {"led light": 5}


class TestLookupRanks:
    def test_キーワードごとに順位を引く(self) -> None:
        index = {"懐中電灯": 694, "懐中電灯 強力": 6876}

        assert lookup_ranks(["懐中電灯", "懐中電灯 強力"], index) == ["694", "6876"]

    def test_見つからないキーワードは空欄にする(self) -> None:
        assert lookup_ranks(["ない語", "懐中電灯"], {"懐中電灯": 694}) == ["", "694"]

    def test_全部見つからなければ空(self) -> None:
        assert lookup_ranks(["ない語"], {}) == []


class TestBuildRankUpdates:
    def test_検索ワードの並びに合わせて順位を書く(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001", "懐中電灯\n懐中電灯 強力")]

        updates = build_rank_updates(values, {"懐中電灯": 694, "懐中電灯 強力": 6876})

        assert updates == {4: {RANK_INDEX: "694\n6876"}}

    def test_既に順位がある行は触らない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001", "懐中電灯", rank="1")]

        assert build_rank_updates(values, {"懐中電灯": 694}) == {}

    def test_検索ワードが無い行は触らない(self) -> None:
        values = [CODE_ROW, LABEL_ROW, UNIT_ROW, _row("B000000001")]

        assert build_rank_updates(values, {"懐中電灯": 694}) == {}

    def test_列コードが無ければ何も書かない(self) -> None:
        values = [["んh"], [""], [""], ["x"]]

        assert build_rank_updates(values, {"懐中電灯": 694}) == {}

    def test_列コードはSEARCH_RANK(self) -> None:
        assert RANK_CODE == "SEARCH_RANK"
