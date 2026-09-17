import argparse
import json

import move_seasonal
from move_seasonal import parse_args, run
from src.domain.value_objects.seasonal_verdicts import SeasonalVerdicts
from src.infrastructure.claude_cli import ClaudeCliError

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL", "TITLE_BUY"]
LABEL_ROW = ["", "", "ASIN", "", "", "", "商品名", "商品名(BUY)"]
UNIT_ROW = ["", "", "", "", "", "", "", ""]
SHEET = "自動調査1000円以下"


def _row(asin: str, title: str) -> list[str]:
    return ["", "", asin, "", "", "", title, ""]


class FakeRepository:
    def __init__(self, rows: list[list]) -> None:
        self.values = {SHEET: [CODE_ROW, LABEL_ROW, UNIT_ROW, *rows], "季節商品": [CODE_ROW, LABEL_ROW, UNIT_ROW]}
        self.appended: list[tuple[str, list[list]]] = []
        self.deleted: list[tuple[str, list[int]]] = []

    def sheet_titles(self) -> list[str]:
        return list(self.values)

    def read_values(self, sheet_name: str) -> list[list]:
        return self.values[sheet_name]

    def ensure_rows(self, sheet_name: str, last_row_number: int) -> int:
        return 0

    def apply_updates(self, sheet_name: str, updates: dict) -> int:
        self.appended.append((sheet_name, [cells for _, cells in sorted(updates.items())]))
        return sum(len(cells) for cells in updates.values())

    def delete_rows(self, sheet_name: str, row_numbers: list[int]) -> int:
        self.deleted.append((sheet_name, row_numbers))
        return len(row_numbers)


class FakeCli:
    def __init__(self, seasonal: dict[str, bool] | None = None, error: bool = False) -> None:
        self.seasonal = seasonal or {}
        self.error = error
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise ClaudeCliError("boom")
        lines = [line for line in prompt.splitlines() if line[:1].isdigit() and ": " in line]
        answers = []
        for line in lines:
            index, title = line.split(": ", 1)
            answers.append({"index": int(index), "seasonal": self.seasonal.get(title, False)})
        return json.dumps(answers)


class FakeStore:
    def __init__(self, verdicts: SeasonalVerdicts | None = None) -> None:
        self.verdicts = verdicts or SeasonalVerdicts()
        self.saved = 0

    def load(self) -> SeasonalVerdicts:
        return self.verdicts

    def save(self, verdicts: SeasonalVerdicts) -> None:
        self.verdicts = verdicts
        self.saved += 1


def _args(**overrides: object) -> argparse.Namespace:
    base = {"sheet": SHEET, "dry_run": False, "not_seasonal": []}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRun:
    def test_Claudeが季節商品と判定した行だけを移す(self) -> None:
        repository = FakeRepository(
            [_row("B000000001", "ハンディファン 携帯扇風機"), _row("B000000002", "ホコリ取りスポンジ ファンブレード用")]
        )
        cli = FakeCli(seasonal={"ハンディファン 携帯扇風機": True})

        result = run(_args(), repository=repository, cli=cli, store=FakeStore())

        assert result == 0
        assert repository.deleted == [(SHEET, [4])]
        assert [cells[2] for cells in repository.appended[0][1]] == ["B000000001"]

    def test_移した数式は移動先の行を参照する(self) -> None:
        repository = FakeRepository([_row("B000000001", "日傘")])
        repository.values[SHEET][3][3] = "=C4*2"
        repository.values["季節商品"].append(_row("B000000009", "既存の行"))

        run(_args(), repository=repository, cli=FakeCli(seasonal={"日傘": True}), store=FakeStore())

        assert repository.appended[0][1][0][3] == "=C5*2"

    def test_キーワードに当たらない行はClaudeに聞かない(self) -> None:
        repository = FakeRepository([_row("B000000001", "車用ベビーミラー")])
        cli = FakeCli()

        run(_args(), repository=repository, cli=cli, store=FakeStore())

        assert cli.prompts == []

    def test_判定済みのASINはClaudeに聞き直さない(self) -> None:
        verdicts = SeasonalVerdicts()
        verdicts.record_claude("B000000001", True)
        repository = FakeRepository([_row("B000000001", "日傘")])
        cli = FakeCli()

        run(_args(), repository=repository, cli=cli, store=FakeStore(verdicts))

        assert cli.prompts == []
        assert repository.deleted == [(SHEET, [4])]

    def test_人が季節商品ではないとした行は移さない(self) -> None:
        verdicts = SeasonalVerdicts()
        verdicts.record_human("B000000001", False)
        repository = FakeRepository([_row("B000000001", "洗濯ネット 毛布用")])
        cli = FakeCli(seasonal={"洗濯ネット 毛布用": True})

        run(_args(), repository=repository, cli=cli, store=FakeStore(verdicts))

        assert cli.prompts == []
        assert repository.deleted == []

    def test_判定を保存する(self) -> None:
        store = FakeStore()
        repository = FakeRepository([_row("B000000001", "日傘")])

        run(_args(), repository=repository, cli=FakeCli(seasonal={"日傘": True}), store=store)

        assert store.saved >= 1
        assert store.verdicts.is_seasonal("B000000001") is True

    def test_Claudeが失敗したら移さず1を返す(self) -> None:
        repository = FakeRepository([_row("B000000001", "日傘")])

        result = run(_args(), repository=repository, cli=FakeCli(error=True), store=FakeStore())

        assert result == 1
        assert repository.deleted == []
        assert repository.appended == []

    def test_dryrunでは移さず判定も保存しない(self) -> None:
        store = FakeStore()
        repository = FakeRepository([_row("B000000001", "日傘")])

        run(_args(dry_run=True), repository=repository, cli=FakeCli(seasonal={"日傘": True}), store=store)

        assert repository.deleted == []
        assert store.saved == 0


class TestNotSeasonal:
    def test_人の判断として記録しシートは触らない(self) -> None:
        store = FakeStore()
        repository = FakeRepository([_row("B000000001", "日傘")])
        cli = FakeCli()

        result = run(
            _args(not_seasonal=["B000000001", "https://www.amazon.co.jp/dp/B000000002"]),
            repository=repository,
            cli=cli,
            store=store,
        )

        assert result == 0
        assert store.verdicts.is_seasonal("B000000001") is False
        assert store.verdicts.is_seasonal("B000000002") is False
        assert cli.prompts == []
        assert repository.deleted == []

    def test_ASINを読めなければ1を返す(self) -> None:
        store = FakeStore()

        result = run(_args(not_seasonal=["xyz"]), repository=FakeRepository([]), cli=FakeCli(), store=store)

        assert result == 1
        assert store.saved == 0

    def test_引数で複数渡せる(self) -> None:
        assert parse_args(["--not-seasonal", "B000000001", "B000000002"]).not_seasonal == [
            "B000000001",
            "B000000002",
        ]

    def test_既定は空(self) -> None:
        assert parse_args([]).not_seasonal == []

    def test_保存先はdata配下(self) -> None:
        assert move_seasonal.VERDICTS_PATH.parent.name == "data"
