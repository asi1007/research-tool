from __future__ import annotations

import pytest

from src.domain.entities.rival_candidate import RANKING, RELATED, SEARCH, RivalCandidate, RivalPlacement
from src.domain.value_objects.asin import Asin
from src.usecases.rival_research import (
    build_rival_updates,
    merge_candidates,
    plan_rival_rows,
    rival_row_numbers,
)


def placement(source: str, rank: int) -> RivalPlacement:
    return RivalPlacement(source=source, rank=rank)


class TestMergeCandidates:
    def test_同じASINが複数経路に出たら1件へまとめる(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [("B0F1N7BCGY", "Luxspire 歯ブラシスタンド", 1)],
                SEARCH: [("B0F1N7BCGY", "Luxspire 歯ブラシスタンド", 3)],
                RANKING: [("B0F1N7BCGY", "Luxspire 歯ブラシスタンド", 4)],
            }
        )

        assert len(merged) == 1
        assert merged[0].rank_label() == "関連1\n検索3\nランキング4"

    def test_経路ごとに上位から件数を絞る(self) -> None:
        merged = merge_candidates(
            {SEARCH: [(f"B00000000{i}", f"商品{i}", i) for i in range(1, 6)]},
            limit_per_source=3,
        )

        assert [c.asin.value for c in merged] == ["B000000001", "B000000002", "B000000003"]

    def test_件数の上限は経路ごとに独立して数える(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [("B000000001", "A", 1), ("B000000002", "B", 2), ("B000000003", "C", 3)],
                SEARCH: [("B000000004", "D", 1), ("B000000005", "E", 2), ("B000000006", "F", 3)],
            },
            limit_per_source=3,
        )

        assert len(merged) == 6

    def test_並び順は経路順そのなかは順位順(self) -> None:
        merged = merge_candidates(
            {
                RANKING: [("B000000003", "C", 1)],
                SEARCH: [("B000000002", "B", 5)],
                RELATED: [("B000000001", "A", 7)],
            }
        )

        assert [c.asin.value for c in merged] == ["B000000001", "B000000002", "B000000003"]

    def test_複数経路に出る候補は最初に見つかった経路の位置へ置く(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [("B000000002", "B", 2)],
                SEARCH: [("B000000001", "A", 1), ("B000000002", "B", 9)],
            }
        )

        assert [c.asin.value for c in merged] == ["B000000002", "B000000001"]

    def test_ASINとして読めない値は捨てる(self) -> None:
        merged = merge_candidates({SEARCH: [("こわれた", "X", 1), ("B000000001", "A", 2)]})

        assert [c.asin.value for c in merged] == ["B000000001"]

    def test_自社ASINは候補から外す(self) -> None:
        merged = merge_candidates(
            {SEARCH: [("B000000001", "自社", 1), ("B000000002", "他社", 2)]},
            exclude=Asin.parse("B000000001"),
        )

        assert [c.asin.value for c in merged] == ["B000000002"]

    def test_自社を外しても件数の上限は残りで満たす(self) -> None:
        merged = merge_candidates(
            {
                SEARCH: [
                    ("B000000001", "自社", 1),
                    ("B000000002", "A", 2),
                    ("B000000003", "B", 3),
                    ("B000000004", "C", 4),
                ]
            },
            exclude=Asin.parse("B000000001"),
            limit_per_source=3,
        )

        assert [c.asin.value for c in merged] == ["B000000002", "B000000003", "B000000004"]

    def test_順位が数値でない候補は捨てる(self) -> None:
        merged = merge_candidates({SEARCH: [("B000000001", "A", None), ("B000000002", "B", 2)]})

        assert [c.asin.value for c in merged] == ["B000000002"]


class TestRivalRowNumbers:
    def test_挿入する行番号は対象行の直下から連番になる(self) -> None:
        assert rival_row_numbers(base_row=10, count=3) == [11, 12, 13]

    def test_候補が無ければ空(self) -> None:
        assert rival_row_numbers(base_row=10, count=0) == []


class TestBuildRivalUpdates:
    def test_ASINと順位を対象の列へ入れる(self) -> None:
        candidates = [
            RivalCandidate(
                asin=Asin.parse("B000000001"),
                title="A",
                placements=(placement(SEARCH, 2),),
            )
        ]

        updates = build_rival_updates(candidates, base_row=10, asin_column=2, rank_column=5)

        assert updates == {11: {2: "B000000001", 5: "検索2"}}

    def test_候補が無ければ空(self) -> None:
        assert build_rival_updates([], base_row=10, asin_column=2, rank_column=5) == {}


class TestPlanRivalRows:
    def test_対象行の直下へ空行を挿入する計画を返す(self) -> None:
        plan = plan_rival_rows(base_row=10, count=3)

        assert plan == {"start_row": 11, "count": 3}

    def test_候補が無ければ挿入しない(self) -> None:
        assert plan_rival_rows(base_row=10, count=0) is None


class TestPlacementsAreComplete:
    def test_採用件数から漏れた経路の順位もラベルに載せる(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [
                    ("B000000001", "A", 1),
                    ("B000000002", "B", 2),
                    ("B000000003", "C", 3),
                    ("B000000009", "Z", 6),
                ],
                SEARCH: [("B000000009", "Z", 5)],
            },
            limit_per_source=3,
        )

        found = {c.asin.value: c.rank_label() for c in merged}
        assert found["B000000009"] == "関連6\n検索5"

    def test_どの経路でも上位に入らない候補は採用しない(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [(f"B00000000{i}", f"商品{i}", i) for i in range(1, 5)],
                SEARCH: [(f"B00000000{i}", f"商品{i}", i) for i in range(1, 5)],
            },
            limit_per_source=3,
        )

        assert [c.asin.value for c in merged] == ["B000000001", "B000000002", "B000000003"]

    def test_採用は経路ごとの上位で決まり順位は経路順に並ぶ(self) -> None:
        merged = merge_candidates(
            {
                RELATED: [("B000000001", "A", 4)],
                SEARCH: [("B000000001", "A", 1)],
                RANKING: [("B000000001", "A", 9)],
            },
            limit_per_source=1,
        )

        assert merged[0].rank_label() == "関連4\n検索1\nランキング9"
