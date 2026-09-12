from __future__ import annotations

import pytest

from src.usecases.move_rows import (
    MoveDestination,
    MovePlan,
    build_move_plan,
    locate_rows,
    map_row_to_destination,
    missing_codes,
)


class TestLocateRows:
    def test_ASINで行番号を引く(self) -> None:
        values = [
            ["ASIN_SELL"],
            ["ASIN"],
            [""],
            ["B000000001"],
            ["B000000002"],
        ]

        assert locate_rows(values, asin_column=0, asins=["B000000002"]) == {"B000000002": 5}

    def test_ASIN列がURLでも引ける(self) -> None:
        values = [["ASIN_SELL"], [""], [""], ["https://www.amazon.co.jp/dp/B000000003"]]

        assert locate_rows(values, asin_column=0, asins=["B000000003"]) == {"B000000003": 4}

    def test_同じASINが複数あれば最初の行を返す(self) -> None:
        values = [["ASIN_SELL"], [""], [""], ["B000000001"], ["B000000001"]]

        assert locate_rows(values, asin_column=0, asins=["B000000001"]) == {"B000000001": 4}

    def test_見つからないASINは入らない(self) -> None:
        values = [["ASIN_SELL"], [""], [""], ["B000000001"]]

        assert locate_rows(values, asin_column=0, asins=["B000000009"]) == {}


class TestMapRowToDestination:
    def test_列コードで対応させる(self) -> None:
        source_codes = ["ASIN_SELL", "PRICE_SELL", "TITLE_SELL"]
        dest_codes = ["ASIN_SELL", "TITLE_SELL", "PRICE_SELL"]
        row = ["B000000001", 500, "商品名"]

        mapped = map_row_to_destination(row, source_codes, dest_codes, source_row=4, dest_row=10)

        assert mapped == {0: "B000000001", 1: "商品名", 2: 500}

    def test_移動先に無い列は落とす(self) -> None:
        source_codes = ["ASIN_SELL", "SPEC_LOWEST"]
        dest_codes = ["ASIN_SELL"]
        row = ["B000000001", "20*20cm"]

        mapped = map_row_to_destination(row, source_codes, dest_codes, source_row=4, dest_row=10)

        assert mapped == {0: "B000000001"}

    def test_数式は移動先の行番号へ書き換える(self) -> None:
        source_codes = ["PROFIT", "PRICE_SELL"]
        dest_codes = ["PROFIT", "PRICE_SELL"]
        row = ["=B4-C4", 500]

        mapped = map_row_to_destination(row, source_codes, dest_codes, source_row=4, dest_row=10)

        assert mapped[0] == "=B10-C10"

    def test_数式の列レターは移動先の並びへ読み替える(self) -> None:
        # 元は B=PROFIT C=PRICE_SELL、移動先は B=PRICE_SELL C=PROFIT
        source_codes = ["ASIN_SELL", "PROFIT", "PRICE_SELL"]
        dest_codes = ["ASIN_SELL", "PRICE_SELL", "PROFIT"]
        row = ["B000000001", "=C4*2", 500]

        mapped = map_row_to_destination(row, source_codes, dest_codes, source_row=4, dest_row=10)

        # PRICE_SELL は元の C列、移動先では B列
        assert mapped[2] == "=B10*2"

    def test_空セルは送らない(self) -> None:
        source_codes = ["ASIN_SELL", "PRICE_SELL"]
        dest_codes = ["ASIN_SELL", "PRICE_SELL"]
        row = ["B000000001", "   "]

        mapped = map_row_to_destination(row, source_codes, dest_codes, source_row=4, dest_row=10)

        assert mapped == {0: "B000000001"}


class TestMissingCodes:
    def test_移動先に無い列コードを返す(self) -> None:
        source_codes = ["ASIN_SELL", "SPEC_LOWEST", "RIVAL_RANK"]
        dest_codes = ["ASIN_SELL"]

        assert missing_codes(source_codes, dest_codes) == ["SPEC_LOWEST", "RIVAL_RANK"]

    def test_すべて揃っていれば空(self) -> None:
        assert missing_codes(["ASIN_SELL"], ["ASIN_SELL", "PRICE_SELL"]) == []

    def test_列コードが空の欄は数えない(self) -> None:
        assert missing_codes(["ASIN_SELL", "", "  "], ["ASIN_SELL"]) == []


class TestBuildMovePlan:
    SOURCE = [
        ["ASIN_SELL", "PRICE_SELL", "RIVAL_RANK"],
        ["ASIN", "カート価格", "順位"],
        ["", "", ""],
        ["B000000001", 500, ""],
        ["B000000002", 600, "関連1"],
        ["B000000003", 700, ""],
    ]
    DEST = [
        ["ASIN_SELL", "PRICE_SELL", "RIVAL_RANK"],
        ["ASIN", "カート価格", "順位"],
        ["", "", ""],
        ["B000000099", 900, ""],
    ]

    def test_先頭へ挿入すると移動先の行番号は4から始まる(self) -> None:
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000003"], MoveDestination.TOP, header_rows=3
        )

        assert plan.insert_at == 4
        assert plan.source_rows == [6]
        assert plan.updates[4][0] == "B000000003"

    def test_末尾へ足すと既存の次の行から始まる(self) -> None:
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000003"], MoveDestination.BOTTOM, header_rows=3
        )

        assert plan.insert_at == 5
        assert plan.source_rows == [6]

    def test_自社行の直下のライバル行も連れていく(self) -> None:
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000001"], MoveDestination.TOP, header_rows=3
        )

        # B000000001 の直下の B000000002 は順位があるのでライバル行
        assert plan.source_rows == [4, 5]

    def test_指定順に並べて入れる(self) -> None:
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000003", "B000000001"], MoveDestination.TOP, header_rows=3
        )

        assert plan.updates[4][0] == "B000000003"
        assert plan.updates[5][0] == "B000000001"

    def test_見つからないASINはmissing_asinsへ入る(self) -> None:
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000009"], MoveDestination.TOP, header_rows=3
        )

        assert plan.missing_asins == ["B000000009"]
        assert plan.source_rows == []

    def test_同じ行を二重に運ばない(self) -> None:
        # B000000002 はライバル行として連れて行かれるので、個別指定しても増えない
        plan = build_move_plan(
            self.SOURCE, self.DEST, ["B000000001", "B000000002"], MoveDestination.TOP, header_rows=3
        )

        assert plan.source_rows == [4, 5]

    def test_ASIN列が無ければ例外(self) -> None:
        with pytest.raises(ValueError):
            build_move_plan([["PRICE_SELL"]], self.DEST, ["B000000001"], MoveDestination.TOP, 3)


class TestMovePlan:
    def test_移動件数を数える(self) -> None:
        plan = MovePlan(
            insert_at=4,
            updates={4: {0: "a"}, 5: {0: "b"}},
            source_rows=[10, 11],
            missing_asins=[],
            dropped_codes=[],
        )

        assert plan.row_count == 2
