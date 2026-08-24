from src.infrastructure.cell_highlighter import (
    FILLED_BACKGROUND,
    apply_highlight,
    build_highlight_requests,
)


class FakeWorksheet:
    def __init__(self) -> None:
        self.received: list[dict] = []

    def batch_format(self, formats: list[dict]) -> None:
        self.received = formats


class TestBuildHighlightRequests:
    def test_セルをA1形式のレンジに変換する(self) -> None:
        requests = build_highlight_requests([(5, 0), (5, 6)])
        assert [r["range"] for r in requests] == ["A5", "G5"]

    def test_背景色を指定する(self) -> None:
        requests = build_highlight_requests([(5, 0)])
        assert requests[0]["format"] == {"backgroundColor": FILLED_BACKGROUND}

    def test_行と列の順に並べる(self) -> None:
        requests = build_highlight_requests([(9, 2), (5, 6), (5, 0)])
        assert [r["range"] for r in requests] == ["A5", "G5", "C9"]

    def test_空なら空リストを返す(self) -> None:
        assert build_highlight_requests([]) == []


class TestApplyHighlight:
    def test_ワークシートへまとめて渡す(self) -> None:
        worksheet = FakeWorksheet()
        count = apply_highlight(worksheet, [(5, 0), (5, 6)])
        assert count == 2
        assert [r["range"] for r in worksheet.received] == ["A5", "G5"]

    def test_空なら呼び出さない(self) -> None:
        worksheet = FakeWorksheet()
        assert apply_highlight(worksheet, []) == 0
        assert worksheet.received == []
