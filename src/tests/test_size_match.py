from __future__ import annotations

from src.usecases.size_match import (
    Dimension,
    Match,
    compare,
    extract_dimensions,
    pack_counts,
)


class TestExtractDimensions:
    def test_日本語の幅と長さを拾う(self) -> None:
        text = "【サイズ詳細】 ペンダント本体：幅8mm×長さ16mm、穴径：2.5mm。"

        found = extract_dimensions(text)

        assert Dimension("幅", 8.0) in found
        assert Dimension("長さ", 16.0) in found
        assert Dimension("穴径", 2.5) in found

    def test_中国語の毫米表記を拾う(self) -> None:
        text = "高约16毫米 宽约8毫米 吊孔直径约2.3毫米"

        found = extract_dimensions(text)

        assert Dimension("高", 16.0) in found
        assert Dimension("宽", 8.0) in found
        assert Dimension("吊孔直径", 2.3) in found

    def test_cmはmmへ揃える(self) -> None:
        assert Dimension("直径", 102.0) in extract_dimensions("直径10.2cm")

    def test_掛け算表記はそのまま並びで返す(self) -> None:
        found = extract_dimensions("20*10*3mm の磁石")

        assert [d.millimeters for d in found] == [20.0, 10.0, 3.0]

    def test_寸法が無ければ空(self) -> None:
        assert extract_dimensions("プラスチック製の便利なパーツ") == []

    def test_個数は寸法として拾わない(self) -> None:
        found = extract_dimensions("100個セット")

        assert found == []

    def test_全角数字も読む(self) -> None:
        assert Dimension("幅", 8.0) in extract_dimensions("幅８mm")


class TestPackCounts:
    def test_日本語の入数を拾う(self) -> None:
        assert 100 in pack_counts("透明ヒートン 100個セット")

    def test_中国語の入数を拾う(self) -> None:
        assert 100 in pack_counts("【100个】")

    def test_複数あれば全部返す(self) -> None:
        assert pack_counts("【10个】【100个】【200个】") == [10, 100, 200]

    def test_入数が無ければ空(self) -> None:
        assert pack_counts("透明ヒートン") == []


class TestCompare:
    def test_同じ寸法が揃えば一致(self) -> None:
        amazon = [Dimension("幅", 8.0), Dimension("長さ", 16.0)]
        supplier = [Dimension("宽", 8.0), Dimension("高", 16.0)]

        result = compare(amazon, supplier)

        assert result.verdict is Match.SAME
        assert result.unmatched == []

    def test_許容差の中なら一致とみなす(self) -> None:
        # 2.5mm と 2.3mm は成形品のばらつきの範囲
        result = compare([Dimension("穴径", 2.5)], [Dimension("直径", 2.3)])

        assert result.verdict is Match.SAME

    def test_許容差を超えれば不一致(self) -> None:
        result = compare([Dimension("長さ", 16.0)], [Dimension("高", 25.0)])

        assert result.verdict is Match.DIFFERENT
        assert result.unmatched == [16.0]

    def test_一部だけ合えば要確認(self) -> None:
        amazon = [Dimension("幅", 8.0), Dimension("長さ", 16.0)]
        supplier = [Dimension("宽", 8.0)]

        result = compare(amazon, supplier)

        assert result.verdict is Match.PARTIAL

    def test_どちらかが空なら判定不能(self) -> None:
        assert compare([], [Dimension("宽", 8.0)]).verdict is Match.UNKNOWN
        assert compare([Dimension("幅", 8.0)], []).verdict is Match.UNKNOWN

    def test_一致した組を返す(self) -> None:
        result = compare([Dimension("幅", 8.0)], [Dimension("宽", 8.2)])

        assert result.matched == [(8.0, 8.2)]

    def test_許容差は絶対値と割合の大きいほうを使う(self) -> None:
        # 100mm に対する 3mm 差は割合では 3% なので許容、絶対値0.5mmだけだと弾かれてしまう
        assert compare([Dimension("長さ", 100.0)], [Dimension("高", 103.0)]).verdict is Match.SAME
        # 小さい寸法は絶対値で見る。2.5 と 2.3 の差 0.2mm は許容
        assert compare([Dimension("穴径", 2.5)], [Dimension("直径", 2.3)]).verdict is Match.SAME
        # 同じ 0.2mm 差でも 2.5 と 3.0 は離れすぎ
        assert compare([Dimension("穴径", 2.5)], [Dimension("直径", 3.4)]).verdict is Match.DIFFERENT
