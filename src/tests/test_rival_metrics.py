from __future__ import annotations

from src.usecases.rival_metrics import (
    RivalMetric,
    Strength,
    月商,
    build_metric,
    rank_rivals,
    summarize,
)


def _current(new=1500, buy_box=1200, rating=43, reviews=120) -> list[int]:
    """Keepa の stats.current を組む。1=New 16=評価(10倍) 17=レビュー数 18=カート価格"""
    row = [-1] * 36
    row[1], row[16], row[17], row[18] = new, rating, reviews, buy_box
    return row


def _product(**overrides) -> dict:
    base = {
        "asin": "B000000001",
        "title": "テスト商品",
        "brand": "TestBrand",
        "monthlySold": 300,
        "stats": {"current": _current()},
    }
    base.update(overrides)
    return base


class TestBuildMetric:
    def test_価格はカート価格を優先する(self) -> None:
        # stats.current[18] がカート価格、[1] が New
        metric = build_metric(_product())

        assert metric.price == 1200

    def test_カート価格が無ければNewを使う(self) -> None:
        metric = build_metric(_product(stats={"current": _current(buy_box=-1)}))

        assert metric.price == 1500

    def test_価格が取れなければNone(self) -> None:
        metric = build_metric(_product(stats={"current": _current(new=-1, buy_box=-1)}))

        assert metric.price is None

    def test_評価は10分の1にして返す(self) -> None:
        assert build_metric(_product()).rating == 4.3

    def test_評価が無ければNone(self) -> None:
        assert build_metric(_product(stats={"current": _current(rating=-1)})).rating is None

    def test_レビュー数はcurrentの17番から取る(self) -> None:
        # rating=1 を付けずに引くと -1 のままなので None になる
        assert build_metric(_product()).review_count == 120
        assert build_metric(_product(stats={"current": _current(reviews=-1)})).review_count is None

    def test_1万円を超える価格もそのまま返す(self) -> None:
        # 日本は円そのまま。セント単位の国と取り違えて100で割ってはいけない
        assert build_metric(_product(stats={"current": _current(buy_box=25800)})).price == 25800

    def test_月販が無ければNone(self) -> None:
        assert build_metric(_product(monthlySold=None)).monthly_sold is None


class Test月商:
    def test_月販と価格の積(self) -> None:
        assert 月商(300, 1200) == 360000

    def test_どちらかが無ければNone(self) -> None:
        assert 月商(None, 1200) is None
        assert 月商(300, None) is None


class TestRankRivals:
    def test_月商の大きい順に並べる(self) -> None:
        rivals = [
            RivalMetric("A", "小", "b", 100, 500, 10, 4.0),
            RivalMetric("B", "大", "b", 1000, 2000, 10, 4.0),
            RivalMetric("C", "中", "b", 500, 1000, 10, 4.0),
        ]

        assert [r.asin for r in rank_rivals(rivals)] == ["B", "C", "A"]

    def test_月商が取れない行は末尾へ回す(self) -> None:
        rivals = [
            RivalMetric("A", "不明", "b", None, None, 10, 4.0),
            RivalMetric("B", "あり", "b", 100, 500, 10, 4.0),
        ]

        assert [r.asin for r in rank_rivals(rivals)] == ["B", "A"]

    def test_上限件数で切る(self) -> None:
        rivals = [RivalMetric(f"A{i}", "x", "b", i, 100, 1, 4.0) for i in range(10)]

        assert len(rank_rivals(rivals, limit=3)) == 3


class TestStrength:
    def test_レビューが少なく月商が大きければ狙い目(self) -> None:
        metric = RivalMetric("A", "x", "b", 500, 1500, 5, 4.0)

        assert metric.strength is Strength.WEAK

    def test_レビューが多ければ強敵(self) -> None:
        metric = RivalMetric("A", "x", "b", 500, 1500, 300, 4.5)

        assert metric.strength is Strength.STRONG

    def test_売れていなければ対象外(self) -> None:
        metric = RivalMetric("A", "x", "b", 5, 1500, 10, 4.0)

        assert metric.strength is Strength.MINOR

    def test_月販が不明なら判定しない(self) -> None:
        metric = RivalMetric("A", "x", "b", None, 1500, 10, 4.0)

        assert metric.strength is Strength.UNKNOWN


class TestSummarize:
    def test_中央値と合計を出す(self) -> None:
        rivals = [
            RivalMetric("A", "x", "b", 100, 1000, 10, 4.0),
            RivalMetric("B", "x", "b", 200, 2000, 20, 4.2),
            RivalMetric("C", "x", "b", 300, 3000, 30, 4.4),
        ]

        summary = summarize(rivals)

        assert summary["件数"] == 3
        assert summary["価格中央値"] == 2000
        assert summary["レビュー中央値"] == 20
        assert summary["月商合計"] == 100 * 1000 + 200 * 2000 + 300 * 3000

    def test_値が取れない行は中央値から外す(self) -> None:
        rivals = [
            RivalMetric("A", "x", "b", None, None, None, None),
            RivalMetric("B", "x", "b", 200, 2000, 20, 4.2),
        ]

        summary = summarize(rivals)

        assert summary["価格中央値"] == 2000
        assert summary["件数"] == 2

    def test_空なら件数0(self) -> None:
        assert summarize([])["件数"] == 0
