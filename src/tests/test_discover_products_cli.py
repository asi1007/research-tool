import argparse
import subprocess
import sys
from datetime import datetime, timezone

import discover_products
from discover_products import fetch_command, run
from src.domain.value_objects.asin import Asin


class TestFetchCommand:
    def test_同じvenvのpythonでfetch_productsを呼ぶ(self) -> None:
        command = fetch_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("fetch_products.py")
        assert command[2:] == ["--sheet", "自動調査", "--interval", "auto"]


class FakeKeepa:
    def __init__(self, found: list[Asin]) -> None:
        self.found = found
        self.calls = 0

    def find_asins(self, criteria, now) -> list[Asin]:
        self.calls += 1
        return self.found


class FakeRepository:
    def __init__(self, known: set[str] | None = None, values: list[list] | None = None) -> None:
        self.known = known or set()
        self.values = values if values is not None else [["んh"], [], []]
        self.ensure_rows_calls: list[tuple[str, int]] = []
        self.apply_updates_calls: list[tuple[str, dict]] = []
        self.read_values_calls: list[str] = []

    def read_all_values(self) -> dict[str, list[list]]:
        return {"候補": [["んh", "ASIN_SELL"], ["", "ASIN"], ["", ""]] + [["", asin] for asin in self.known]}

    def read_values(self, sheet_name: str) -> list[list]:
        self.read_values_calls.append(sheet_name)
        return self.values

    def ensure_rows(self, sheet_name: str, last_row_number: int) -> int:
        self.ensure_rows_calls.append((sheet_name, last_row_number))
        return 0

    def apply_updates(self, sheet_name: str, updates: dict) -> int:
        self.apply_updates_calls.append((sheet_name, updates))
        return sum(len(columns) for columns in updates.values())


def _args(**overrides: object) -> argparse.Namespace:
    base = {"limit": None, "dry_run": False, "no_fetch": False}
    base.update(overrides)
    return argparse.Namespace(**base)


APPEND_SHEET = [
    ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL",
     "TITLE_BUY", "NOTE_BUY_OTHER8", "NOTE_BUY_OTHER7", "", "NOTE_BUY_OTHER2"],
    ["", "", "ASIN", "", "", "", "", "", "", "", "", ""],
    ["0", "1", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
]


class TestRun:
    def test_dryrunのときapply_updatesとensure_rowsが呼ばれない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000001")])
        repository = FakeRepository(values=APPEND_SHEET)
        called = {"subprocess": False}
        monkeypatch.setattr(
            discover_products.subprocess,
            "run",
            lambda *a, **k: called.update(subprocess=True) or subprocess.CompletedProcess(a, 0),
        )

        result = run(_args(dry_run=True), repository=repository, keepa=keepa)

        assert result == 0
        assert repository.apply_updates_calls == []
        assert repository.ensure_rows_calls == []
        assert called["subprocess"] is False

    def test_freshが空のとき書き込まずfetchは呼ばれる(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000001")])
        repository = FakeRepository(known={"B000000001"}, values=APPEND_SHEET)
        recorded_commands: list[list[str]] = []
        monkeypatch.setattr(
            discover_products.subprocess,
            "run",
            lambda command, **k: recorded_commands.append(command) or subprocess.CompletedProcess(command, 0),
        )

        result = run(_args(), repository=repository, keepa=keepa)

        assert result == 0
        assert repository.apply_updates_calls == []
        assert repository.ensure_rows_calls == []
        assert len(recorded_commands) == 1

    def test_no_fetchのときsubprocess_runが呼ばれない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000009")])
        repository = FakeRepository(values=APPEND_SHEET)
        called = {"subprocess": False}
        monkeypatch.setattr(
            discover_products.subprocess,
            "run",
            lambda *a, **k: called.update(subprocess=True) or subprocess.CompletedProcess(a, 0),
        )

        result = run(_args(no_fetch=True), repository=repository, keepa=keepa)

        assert result == 0
        assert len(repository.apply_updates_calls) == 1
        assert called["subprocess"] is False
