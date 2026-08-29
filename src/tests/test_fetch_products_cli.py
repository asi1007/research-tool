import argparse

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
