import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

import discover_products
from discover_products import (
    fetch_command,
    keyword_command,
    run,
    seasonal_command,
    shorten_command,
)
from src.domain.entities.product_info import ProductInfo
from src.domain.value_objects.asin import Asin


class TestFetchCommand:
    def test_同じvenvのpythonでfetch_productsを呼ぶ(self) -> None:
        command = fetch_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("fetch_products.py")
        assert command[2:] == ["--sheet", "自動調査", "--interval", "auto"]


class TestKeywordCommand:
    def test_同じvenvのpythonでfill_keywordsを呼ぶ(self) -> None:
        command = keyword_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("fill_keywords.py")
        assert command[2:] == ["--sheet", "自動調査"]


class TestSeasonalCommand:
    def test_同じvenvのpythonでmove_seasonalを呼ぶ(self) -> None:
        command = seasonal_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("move_seasonal.py")
        assert command[2:] == ["--sheet", "自動調査"]


class TestShortenCommand:
    def test_同じvenvのpythonでshorten_titlesを呼ぶ(self) -> None:
        command = shorten_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("shorten_titles.py")
        assert command[2:] == ["--sheet", "自動調査"]


class FakeKeepa:
    def __init__(self, found: list[Asin], products: list | None = None) -> None:
        self.found = found
        self.products = products
        self.calls = 0
        self.criteria: list[object] = []
        self.max_pages: list[int] = []
        self.fetched: list[list[Asin]] = []

    def find_asins(self, criteria, now, max_pages=20) -> list[Asin]:
        self.calls += 1
        self.criteria.append(criteria)
        self.max_pages.append(max_pages)
        return self.found

    def fetch_products(self, asins: list[Asin]) -> list:
        self.fetched.append(asins)
        if self.products is not None:
            return self.products
        return [
            ProductInfo(asin=asin, buy_box_price=2000, monthly_sold=1000) for asin in asins
        ]


class FakeRepository:
    def __init__(self, known: set[str] | None = None, values: list[list] | None = None) -> None:
        self.known = known or set()
        self.values = values if values is not None else [["んh"], [], []]
        self.ensure_rows_calls: list[tuple[str, int]] = []
        self.apply_updates_calls: list[tuple[str, dict]] = []
        self.read_values_calls: list[str] = []
        self.titles = ["候補", "自動調査1000円以下", "自動調査1000円-2000円"]

    def sheet_titles(self) -> list[str]:
        return self.titles

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
    base = {
        "limit": None,
        "dry_run": False,
        "no_fetch": False,
        "no_shorten": False,
        "no_keywords": False,
        "no_seasonal": False,
        "sheet": None,
        "all_sheets": False,
        "max_pages": None,
    }
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
        assert len(recorded_commands) == 4

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


class TestShortenTitles:
    def test_商品情報の取得に続けて短縮名を書き込む(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000010")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(), repository=repository, keepa=keepa)

        assert [Path(command[1]).name for command in recorded] == [
            "fetch_products.py",
            "shorten_titles.py",
            "fill_keywords.py",
            "move_seasonal.py",
        ]

    def test_no_seasonalのとき季節商品へ移さない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000015")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(no_seasonal=True), repository=repository, keepa=keepa)

        assert "move_seasonal.py" not in [Path(command[1]).name for command in recorded]

    def test_no_keywordsのとき検索ワードは書き込まない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000014")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(no_keywords=True), repository=repository, keepa=keepa)

        assert [Path(command[1]).name for command in recorded] == [
            "fetch_products.py",
            "shorten_titles.py",
            "move_seasonal.py",
        ]

    def test_no_shortenのとき短縮名は書き込まない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000011")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(no_shorten=True), repository=repository, keepa=keepa)

        assert [Path(command[1]).name for command in recorded] == [
            "fetch_products.py",
            "fill_keywords.py",
            "move_seasonal.py",
        ]

    def test_no_fetchのとき短縮名も書き込まない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000012")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(no_fetch=True), repository=repository, keepa=keepa)

        assert recorded == []

    def test_商品情報の取得が失敗しても短縮名は書き込む(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000013")])
        repository = FakeRepository(values=APPEND_SHEET)
        recorded: list[list[str]] = []

        def fake_run(command, **kwargs) -> subprocess.CompletedProcess:
            recorded.append(command)
            failed = Path(command[1]).name == "fetch_products.py"
            return subprocess.CompletedProcess(command, 1 if failed else 0)

        monkeypatch.setattr(discover_products.subprocess, "run", fake_run)

        result = run(_args(), repository=repository, keepa=keepa)

        assert [Path(command[1]).name for command in recorded] == [
            "fetch_products.py",
            "shorten_titles.py",
            "fill_keywords.py",
            "move_seasonal.py",
        ]
        assert result == 1


class TestBandSelection:
    def test_既定は1000円以下タブで1円から1000円を探す(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000001")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(), repository=repository, keepa=keepa)

        criteria = keepa.criteria[0]
        assert (criteria.min_price_yen, criteria.max_price_yen) == (1, 1000)
        assert repository.apply_updates_calls[0][0] == "自動調査1000円以下"
        assert recorded[0][2:] == ["--sheet", "自動調査1000円以下", "--interval", "auto"]
        assert recorded[1][2:] == ["--sheet", "自動調査1000円以下"]
        assert recorded[2][2:] == ["--sheet", "自動調査1000円以下"]
        assert recorded[3][2:] == ["--sheet", "自動調査1000円以下"]

    def test_タブ名から価格帯を読み取って探す(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000002")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        run(_args(sheet="自動調査1000円-2000円"), repository=repository, keepa=keepa)

        criteria = keepa.criteria[0]
        assert (criteria.min_price_yen, criteria.max_price_yen) == (1001, 2000)
        assert repository.apply_updates_calls[0][0] == "自動調査1000円-2000円"
        assert recorded[0][2:] == ["--sheet", "自動調査1000円-2000円", "--interval", "auto"]

    def test_価格帯を読めないタブ名は実行せず1を返す(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000003")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        result = run(_args(sheet="候補"), repository=repository, keepa=keepa)

        assert result == 1
        assert keepa.calls == 0
        assert repository.apply_updates_calls == []

    def test_allは自動調査タブを価格の安い順に処理する(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000004")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record(recorded := []))

        result = run(_args(all_sheets=True), repository=repository, keepa=keepa)

        assert result == 0
        assert keepa.calls == 2
        assert [
            (criteria.min_price_yen, criteria.max_price_yen) for criteria in keepa.criteria
        ] == [(1, 1000), (1001, 2000)]
        assert [command[3] for command in recorded] == ["自動調査1000円以下"] * 4 + [
            "自動調査1000円-2000円"
        ] * 4

    def test_allのとき前のタブで積んだASINは次のタブへ積まない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000005")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(all_sheets=True), repository=repository, keepa=keepa)

        assert [call[0] for call in repository.apply_updates_calls] == ["自動調査1000円以下"]


def _record(recorded: list[list[str]]):
    def fake_run(command, **kwargs) -> subprocess.CompletedProcess:
        recorded.append(command)
        return subprocess.CompletedProcess(command, 0)

    return fake_run


class TestDryRunSkipsLookup:
    def test_dryrunでは実測を問い合わせない(self, monkeypatch) -> None:
        # 実測は1件1トークン。書き込まない dry-run で消費しない
        keepa = FakeKeepa([Asin("B000000031"), Asin("B000000032")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(dry_run=True), repository=repository, keepa=keepa)

        assert keepa.fetched == []


class TestRevenueFilter:
    def test_月商が基準に満たないASINは積まない(self, monkeypatch) -> None:
        keepa = FakeKeepa(
            [Asin("B000000021"), Asin("B000000022")],
            products=[
                ProductInfo(asin=Asin("B000000021"), buy_box_price=900, monthly_sold=600),
                ProductInfo(asin=Asin("B000000022"), buy_box_price=900, monthly_sold=100),
            ],
        )
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(no_fetch=True), repository=repository, keepa=keepa)

        written = repository.apply_updates_calls[0][1]
        assert [columns[2] for columns in written.values()] == ["B000000021"]

    def test_既知のASINは実測を問い合わせない(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000021"), Asin("B000000022")])
        repository = FakeRepository(known={"B000000021"}, values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(no_fetch=True), repository=repository, keepa=keepa)

        assert [str(asin) for asin in keepa.fetched[0]] == ["B000000022"]


class TestMaxPages:
    def test_既定はKeepaクライアントの上限に任せる(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000041")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(dry_run=True), repository=repository, keepa=keepa)

        assert keepa.max_pages == [discover_products.DEFAULT_MAX_PAGES]

    def test_ページ数を絞れる(self, monkeypatch) -> None:
        keepa = FakeKeepa([Asin("B000000042")])
        repository = FakeRepository(values=APPEND_SHEET)
        monkeypatch.setattr(discover_products.subprocess, "run", _record([]))

        run(_args(dry_run=True, max_pages=1), repository=repository, keepa=keepa)

        assert keepa.max_pages == [1]
