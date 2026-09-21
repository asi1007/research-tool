from __future__ import annotations

from src.usecases.row_relocator import relocate_updates


HEADER = [["CODE", "CODE"], ["", ""], ["ASIN", "商品名"]]


class TestRelocateUpdates:
    def test_行が動いていなければそのまま(self) -> None:
        values = HEADER + [["B000000001", ""], ["B000000002", ""]]

        updates, missing, _ = relocate_updates(
            values, asin_column=0, planned=[("B000000001", {1: "A"})], header_rows=3
        )

        assert updates == {4: {1: "A"}}
        assert missing == []

    def test_行がずれていたら現在の行番号へ付け直す(self) -> None:
        # 読み取り後に上へ1行挿入され、B000000002 が5行目から6行目へ動いた状況
        values = HEADER + [["B000000009", ""], ["B000000001", ""], ["B000000002", ""]]

        updates, missing, _ = relocate_updates(
            values, asin_column=0, planned=[("B000000002", {1: "B"})], header_rows=3
        )

        assert updates == {6: {1: "B"}}

    def test_消えたASINは書かずに返す(self) -> None:
        values = HEADER + [["B000000001", ""]]

        updates, missing, _ = relocate_updates(
            values, asin_column=0, planned=[("B000000404", {1: "X"})], header_rows=3
        )

        assert updates == {}
        assert missing == ["B000000404"]

    def test_ASIN列がURLでも引ける(self) -> None:
        values = HEADER + [["https://www.amazon.co.jp/dp/B000000001", ""]]

        updates, _, _ = relocate_updates(
            values, asin_column=0, planned=[("B000000001", {1: "A"})], header_rows=3
        )

        assert updates == {4: {1: "A"}}

    def test_書くものが無ければ空(self) -> None:
        assert relocate_updates(HEADER, asin_column=0, planned=[], header_rows=3) == ({}, [], [])


class TestDuplicateAsin:
    def test_同じASINの行が複数あるときは書かない(self) -> None:
        # 同一商品を別行で追っていることがある（URL だけの行など）。
        # 最初の行へ黙って書くと、読み取ったのと別の行を上書きする
        values = HEADER + [["B000000001", ""], ["B000000002", ""], ["B000000001", ""]]

        updates, missing, ambiguous = relocate_updates(
            values, asin_column=0, planned=[("B000000001", {1: "A"})], header_rows=3
        )

        assert updates == {}
        assert missing == []
        assert ambiguous == ["B000000001"]

    def test_重複していない行は書ける(self) -> None:
        values = HEADER + [["B000000001", ""], ["B000000002", ""], ["B000000001", ""]]

        updates, missing, ambiguous = relocate_updates(
            values, asin_column=0, planned=[("B000000002", {1: "B"})], header_rows=3
        )

        assert updates == {5: {1: "B"}}
        assert ambiguous == []

    def test_URLで書かれた同一商品も重複として扱う(self) -> None:
        # B列に商品URLだけが入った行がある。Asin.parse が URL から ASIN を抜くので
        # 素の ASIN 行と同じ商品として突き合う
        values = HEADER + [
            ["B0DCJ7LY9M", ""],
            ["https://www.amazon.co.jp/dp/B0DCJ7LY9M/ref=zg_bs_g", ""],
        ]

        updates, missing, ambiguous = relocate_updates(
            values, asin_column=0, planned=[("B0DCJ7LY9M", {1: "A"})], header_rows=3
        )

        assert updates == {}
        assert ambiguous == ["B0DCJ7LY9M"]
