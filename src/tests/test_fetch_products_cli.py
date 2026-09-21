import argparse

import fetch_products
from fetch_products import run_sheets
from src.usecases.bulk_fetch_products import SheetResult


class FakeUsecase:
    def __init__(self, failing_sheets: set[str] | None = None) -> None:
        self.failing_sheets = failing_sheets or set()
        self.executed: list[str] = []

    def execute(self, sheet_name: str, limit: int | None = None) -> SheetResult:
        self.executed.append(sheet_name)
        if sheet_name in self.failing_sheets:
            raise RuntimeError(f"boom: {sheet_name}")
        return SheetResult(sheet_name=sheet_name)

    def count_targets(self, sheet_name: str) -> SheetResult:
        return self.execute(sheet_name)


def _args(**overrides: object) -> argparse.Namespace:
    base = {"count_only": False, "limit": None, "dry_run": False}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRunSheets:
    def test_全シート成功なら0を返す(self) -> None:
        usecase = FakeUsecase()

        assert run_sheets(usecase, ["優先", "候補"], _args()) == 0
        assert usecase.executed == ["優先", "候補"]

    def test_1シートでも例外が出たら1を返す(self) -> None:
        usecase = FakeUsecase(failing_sheets={"候補"})

        assert run_sheets(usecase, ["優先", "候補"], _args()) == 1

    def test_失敗しても残りのシートは処理を続ける(self) -> None:
        usecase = FakeUsecase(failing_sheets={"優先"})

        run_sheets(usecase, ["優先", "候補"], _args())

        assert usecase.executed == ["優先", "候補"]


SHEET_TITLES = [
    "リリース",
    "優先",
    "自動調査500円-700円",
    "自動調査500円以下",
    "1000円周辺",
    "単価1500~",
    "季節商品",
    "候補外",
    "保留",
]


def _all_args() -> argparse.Namespace:
    return argparse.Namespace(sheets=None, all=True)


class TestResolveSheets:
    def test_自動調査タブを価格の安い順に対象にする(self) -> None:
        # discover が積む先。漏れると後から足した行の商品情報が埋まらない
        sheets = fetch_products.resolve_sheets(_all_args(), SHEET_TITLES)

        assert sheets[:2] == ["自動調査500円以下", "自動調査500円-700円"]

    def test_シートに無いタブは対象にしない(self) -> None:
        # 固定リストはタブのリネームに追従できず WorksheetNotFound で異常終了する
        # （2026-08-30 のリネームに気づけず 2026-09-21 に定期実行が exit 1 になった）
        sheets = fetch_products.resolve_sheets(_all_args(), ["優先"])

        assert sheets == ["優先"]

    def test_移動先タブは対象にしない(self) -> None:
        # 候補外・季節商品・保留は drop_marked の移動先。商品情報を取り直す対象ではない
        sheets = fetch_products.resolve_sheets(_all_args(), SHEET_TITLES)

        assert {"候補外", "季節商品", "保留"} & set(sheets) == set()

    def test_タブを明示したらそれだけを対象にする(self) -> None:
        args = argparse.Namespace(sheets=["優先"], all=True)

        assert fetch_products.resolve_sheets(args, SHEET_TITLES) == ["優先"]
