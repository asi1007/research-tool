import argparse

from shorten_titles import run
from src.infrastructure.claude_cli import ClaudeCliError

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY"]
LABEL_ROW = ["", "", "ASIN", "", "", "画像URL", "商品名", "商品名(BUY)"]
UNIT_ROW = ["0", "1", "", "", "", "", "", ""]


def _values(data_rows: list[list[str]]) -> list[list[str]]:
    return [CODE_ROW, LABEL_ROW, UNIT_ROW, *data_rows]


class FakeRepository:
    def __init__(self, sheet_values: dict[str, list[list]]) -> None:
        self.sheet_values = sheet_values
        self.apply_updates_calls: list[tuple[str, dict]] = []

    def read_all_values(self) -> dict[str, list[list]]:
        return self.sheet_values

    def apply_updates(self, sheet_name: str, updates: dict) -> int:
        self.apply_updates_calls.append((sheet_name, updates))
        return sum(len(columns) for columns in updates.values())


class FakeClaudeCli:
    def __init__(
        self,
        responses: list[str | Exception] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = responses or []
        self.error = error
        self.calls = 0
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


def _args(**overrides: object) -> argparse.Namespace:
    base = {"limit": None, "dry_run": False, "sheet": None}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRun:
    def test_対象が無ければ何も呼ばない(self) -> None:
        repository = FakeRepository({"タブA": _values([])})
        cli = FakeClaudeCli()

        result = run(_args(), repository=repository, cli=cli)

        assert result == 0
        assert cli.calls == 0
        assert repository.apply_updates_calls == []

    def test_正常応答をH列へ書き込む(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", "対象商品"]])
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(responses=['[{"index": 0, "short_title": "短縮商品"}]'])

        result = run(_args(), repository=repository, cli=cli)

        assert result == 0
        assert repository.apply_updates_calls == [("タブA", {4: {7: "短縮商品"}})]

    def test_dry_runでは書き込まない(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", "対象商品"]])
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(responses=['[{"index": 0, "short_title": "短縮商品"}]'])

        result = run(_args(dry_run=True), repository=repository, cli=cli)

        assert result == 0
        assert repository.apply_updates_calls == []
        assert cli.calls == 1

    def test_sheet指定で対象タブを絞る(self) -> None:
        values_a = _values([["B000000001", "", "", "", "", "", "商品A"]])
        values_b = _values([["B000000002", "", "", "", "", "", "商品B"]])
        repository = FakeRepository({"タブA": values_a, "タブB": values_b})
        cli = FakeClaudeCli(responses=['[{"index": 0, "short_title": "短縮A"}]'])

        result = run(_args(sheet="タブA"), repository=repository, cli=cli)

        assert result == 0
        assert repository.apply_updates_calls == [("タブA", {4: {7: "短縮A"}})]

    def test_limitで件数を絞る(self) -> None:
        values = _values(
            [
                ["B000000001", "", "", "", "", "", "商品A"],
                ["B000000002", "", "", "", "", "", "商品B"],
            ]
        )
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(responses=['[{"index": 0, "short_title": "短縮A"}]'])

        result = run(_args(limit=1), repository=repository, cli=cli)

        assert result == 0
        assert len(cli.prompts) == 1
        assert repository.apply_updates_calls == [("タブA", {4: {7: "短縮A"}})]

    def test_claude呼び出しが失敗したバッチは書き込まない(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", "対象商品"]])
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(error=ClaudeCliError("boom"))

        result = run(_args(), repository=repository, cli=cli)

        assert result == 0
        assert repository.apply_updates_calls == []

    def test_応答の検証に失敗したバッチは書き込まない(self) -> None:
        values = _values([["B000000001", "", "", "", "", "", "対象商品"]])
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(responses=["これはJSONではない"])

        result = run(_args(), repository=repository, cli=cli)

        assert result == 0
        assert repository.apply_updates_calls == []

    def test_複数タブの更新はタブごとに1回のapply_updatesにまとまる(self) -> None:
        values_a = _values([["B000000001", "", "", "", "", "", "商品A"]])
        values_b = _values([["B000000002", "", "", "", "", "", "商品B"]])
        repository = FakeRepository({"タブA": values_a, "タブB": values_b})
        cli = FakeClaudeCli(
            responses=[
                '[{"index": 0, "short_title": "短縮A"}, {"index": 1, "short_title": "短縮B"}]'
            ]
        )

        result = run(_args(), repository=repository, cli=cli)

        assert result == 0
        assert len(repository.apply_updates_calls) == 2
        calls = dict(repository.apply_updates_calls)
        assert calls["タブA"] == {4: {7: "短縮A"}}
        assert calls["タブB"] == {4: {7: "短縮B"}}

    def test_後続バッチが失敗しても先行バッチの書き込みは残る(self) -> None:
        values = _values(
            [
                ["B000000001", "", "", "", "", "", "商品A"],
                ["B000000002", "", "", "", "", "", "商品B"],
                ["B000000003", "", "", "", "", "", "商品C"],
            ]
        )
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(
            responses=[
                '[{"index": 0, "short_title": "短縮A"}]',
                '[{"index": 0, "short_title": "短縮B"}]',
                ClaudeCliError("3件目でクラッシュ"),
            ]
        )

        result = run(_args(), repository=repository, cli=cli, batch_size=1)

        assert result == 0
        assert repository.apply_updates_calls == [
            ("タブA", {4: {7: "短縮A"}}),
            ("タブA", {5: {7: "短縮B"}}),
        ]

    def test_後続バッチが応答検証で失敗しても先行バッチの書き込みは残る(self) -> None:
        values = _values(
            [
                ["B000000001", "", "", "", "", "", "商品A"],
                ["B000000002", "", "", "", "", "", "商品B"],
            ]
        )
        repository = FakeRepository({"タブA": values})
        cli = FakeClaudeCli(
            responses=[
                '[{"index": 0, "short_title": "短縮A"}]',
                "これはJSONではない",
            ]
        )

        result = run(_args(), repository=repository, cli=cli, batch_size=1)

        assert result == 0
        assert repository.apply_updates_calls == [("タブA", {4: {7: "短縮A"}})]
