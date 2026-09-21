import argparse
import subprocess
import sys
from pathlib import Path

import pytest

import update_research
from update_research import (
    discover_command,
    drop_command,
    fetch_command,
    formula_command,
    main,
    parse_args,
    run,
    supplier_command,
)


class TestDropCommand:
    def test_同じvenvのpythonでdrop_markedを呼ぶ(self) -> None:
        command = drop_command("自動調査1000円以下")

        assert command[0] == sys.executable
        assert command[1].endswith("drop_marked.py")
        assert command[2:] == ["--sheet", "自動調査1000円以下"]

    def test_タブ指定が無いときはシート引数を渡さない(self) -> None:
        # 各CLIの既定（全タブ）に委ねる。対象タブの一覧をここで二重に持たない
        command = drop_command(None)

        assert command[2:] == []


class TestFetchCommand:
    def test_同じvenvのpythonでfetch_productsを呼ぶ(self) -> None:
        command = fetch_command("自動調査1000円以下")

        assert command[0] == sys.executable
        assert command[1].endswith("fetch_products.py")
        assert command[2:] == [
            "--sheet",
            "自動調査1000円以下",
            "--interval",
            "auto",
            "--limit",
            str(update_research.FETCH_LIMIT_PER_SHEET),
        ]

    def test_タブ指定が無いときはallを付ける(self) -> None:
        # fetch_products は --sheet も --all も無いと対象0件で落ちる
        command = fetch_command(None)

        assert command[2:] == [
            "--all",
            "--interval",
            "auto",
            "--limit",
            str(update_research.FETCH_LIMIT_PER_SHEET),
        ]

    def test_1回に取得する件数に上限をかける(self) -> None:
        # Keepa の補充レートで12秒/件。上限が無いと次の起動までに終わらず後続工程へ進めない
        assert 0 < update_research.FETCH_LIMIT_PER_SHEET <= 50


class TestFormulaCommand:
    def test_同じvenvのpythonでfill_formulasを呼ぶ(self) -> None:
        command = formula_command("自動調査1000円以下")

        assert command[0] == sys.executable
        assert command[1].endswith("fill_formulas.py")
        assert command[2:] == ["--sheet", "自動調査1000円以下"]

    def test_タブ指定が無いときはシート引数を渡さない(self) -> None:
        assert formula_command(None)[2:] == []


class TestSupplierCommand:
    def test_同じvenvのpythonでfind_supplier_autoを呼ぶ(self) -> None:
        command = supplier_command("自動調査1000円以下")

        assert command[0] == sys.executable
        assert command[1].endswith("find_supplier_auto.py")
        assert command[2:] == ["--sheet", "自動調査1000円以下"]

    def test_タブ指定が無いときはシート引数を渡さない(self) -> None:
        assert supplier_command(None)[2:] == []


class TestDiscoverCommand:
    def test_同じvenvのpythonでdiscover_productsを呼ぶ(self) -> None:
        command = discover_command("自動調査1000円以下")

        assert command[0] == sys.executable
        assert command[1].endswith("discover_products.py")
        assert command[2:] == ["--sheet", "自動調査1000円以下", "--max-lookups", "150"]

    def test_タブ指定が無いときは全タブを対象にする(self) -> None:
        # discover_products は --sheet も --all-sheets も無いと1000円以下タブだけになる
        assert discover_command(None)[2:] == ["--all-sheets", "--max-lookups", "150"]


def _args(**overrides: object) -> argparse.Namespace:
    base = {"sheet": None, "discover": False, "dry_run": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def _record(recorded: list[list[str]], failing: str | None = None):
    def fake_run(command, **kwargs) -> subprocess.CompletedProcess:
        recorded.append(command)
        failed = Path(command[1]).name == failing
        return subprocess.CompletedProcess(command, 1 if failed else 0)

    return fake_run


class TestRun:
    def test_印の移動から仕入先調査まで順に呼ぶ(self, monkeypatch) -> None:
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        assert run(_args()) == 0
        assert [Path(command[1]).name for command in recorded] == [
            "drop_marked.py",
            "fetch_products.py",
            "fill_formulas.py",
            "find_supplier_auto.py",
        ]

    def test_discoverを付けると新商品を積んでから更新する(self, monkeypatch) -> None:
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        assert run(_args(discover=True)) == 0
        assert [Path(command[1]).name for command in recorded][0] == "discover_products.py"

    def test_タブを指定すると全工程へ同じタブを渡す(self, monkeypatch) -> None:
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        run(_args(sheet="自動調査1000円以下"))

        assert all("自動調査1000円以下" in command for command in recorded)

    def test_途中が失敗しても残りの工程を実行し非ゼロを返す(self, monkeypatch) -> None:
        # 工程どうしに依存は無い。止めると後続が丸ごと欠測する
        monkeypatch.setattr(
            update_research.subprocess, "run", _record(recorded := [], failing="fetch_products.py")
        )

        assert run(_args()) == 1
        assert [Path(command[1]).name for command in recorded] == [
            "drop_marked.py",
            "fetch_products.py",
            "fill_formulas.py",
            "find_supplier_auto.py",
        ]

    def test_dryrunのときは実行せずコマンドだけ出す(self, monkeypatch) -> None:
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        assert run(_args(dry_run=True)) == 0
        assert recorded == []


class TestParseArgs:
    def test_既定は全タブで新商品の発見をしない(self) -> None:
        args = parse_args([])

        assert (args.sheet, args.discover, args.dry_run) == (None, False, False)

    def test_タブと新商品の発見を指定できる(self) -> None:
        args = parse_args(["--sheet", "自動調査1000円以下", "--discover"])

        assert (args.sheet, args.discover) == ("自動調査1000円以下", True)


class TestLock:
    def test_二重起動のときは工程を実行せず0を返す(self, monkeypatch, tmp_path) -> None:
        # 同じシートへ並行して書き込むと行番号がずれる。前回が走っている間は見送る
        monkeypatch.setattr(update_research, "LOCK_PATH", tmp_path / "lock")
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))
        held = update_research.acquire_lock(update_research.LOCK_PATH)

        assert held is not None
        assert main([]) == 0
        assert recorded == []

    def test_ロックが空いていれば工程を実行する(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(update_research, "LOCK_PATH", tmp_path / "lock")
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        assert main([]) == 0
        assert len(recorded) == 4

    def test_実行が終わればロックは次の起動へ渡る(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(update_research, "LOCK_PATH", tmp_path / "lock")
        monkeypatch.setattr(update_research.subprocess, "run", _record(recorded := []))

        main([])
        main([])

        assert len(recorded) == 8
