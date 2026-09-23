import argparse

from drop_marked import run

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "TITLE_SELL"]
LABEL_ROW = ["", "", "ASIN", "商品名"]
UNIT_ROW = ["", "", "", ""]
SHEET = "自動調査1000円以下"


class FakeRepository:
    def __init__(self, rows: list[list]) -> None:
        self.values = {
            SHEET: [CODE_ROW, LABEL_ROW, UNIT_ROW, *rows],
            "候補外": [CODE_ROW, LABEL_ROW, UNIT_ROW],
            "季節商品": [CODE_ROW, LABEL_ROW, UNIT_ROW],
            "保留": [CODE_ROW, LABEL_ROW, UNIT_ROW],
        }
        self.written: dict[str, list[str]] = {"候補外": [], "季節商品": [], "保留": []}

    def sheet_titles(self) -> list[str]:
        return list(self.values)

    def read_values(self, sheet_name: str) -> list[list]:
        return self.values[sheet_name]

    def ensure_rows(self, sheet_name: str, last_row_number: int) -> int:
        return 0

    def apply_updates(self, sheet_name: str, updates: dict) -> int:
        for _, cells in sorted(updates.items()):
            self.written[sheet_name].append(cells[2])
            row = [""] * len(CODE_ROW)
            for index, cell in cells.items():
                row[index] = cell
            self.values[sheet_name].append(row)
        return len(updates)

    def delete_rows(self, sheet_name: str, row_numbers: list[int]) -> int:
        # 実際のシートと同じく、消した行より下は詰まる
        for row_number in sorted(row_numbers, reverse=True):
            del self.values[sheet_name][row_number - 1]
        return len(row_numbers)


def _args(**overrides: object) -> argparse.Namespace:
    base = {"sheet": SHEET, "dry_run": False}
    base.update(overrides)
    return argparse.Namespace(**base)


class TestRun:
    def test_dは候補外へsは季節商品へ移す(self) -> None:
        repository = FakeRepository(
            [
                ["d", "", "B000000001", "不要"],
                ["", "", "B000000002", "残す"],
                ["s", "", "B000000003", "日傘"],
                ["p", "", "B000000004", "判断保留"],
            ]
        )

        run(_args(), repository=repository)

        assert repository.written == {"候補外": ["B000000001"], "季節商品": ["B000000003"], "保留": ["B000000004"]}
        assert [row[2] for row in repository.values[SHEET][3:]] == ["B000000002"]

    def test_dryrunでは移さない(self) -> None:
        repository = FakeRepository([["s", "", "B000000003", "日傘"]])

        run(_args(dry_run=True), repository=repository)

        assert repository.written == {"候補外": [], "季節商品": [], "保留": []}
        assert len(repository.values[SHEET]) == 4

    def test_sheet省略時は移動先以外のタブをすべて回す(self) -> None:
        repository = FakeRepository([["d", "", "B000000001", "不要"]])
        repository.values["優先"] = [CODE_ROW, LABEL_ROW, UNIT_ROW, ["d", "", "B000000005", "優先の不要"]]
        repository.values["テンプレ(新)"] = [CODE_ROW, LABEL_ROW, UNIT_ROW, ["d", "", "B000000006", "雛形"]]

        run(_args(sheet=None), repository=repository)

        assert repository.written["候補外"] == ["B000000001", "B000000005"]
