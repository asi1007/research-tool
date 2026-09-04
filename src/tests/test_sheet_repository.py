from src.infrastructure.sheet_repository import SheetTable, column_letter


class TestColumnLetter:
    def test_1列目はA(self) -> None:
        assert column_letter(0) == "A"

    def test_26列目はZ(self) -> None:
        assert column_letter(25) == "Z"

    def test_27列目はAA(self) -> None:
        assert column_letter(26) == "AA"

    def test_112列目はDH(self) -> None:
        assert column_letter(111) == "DH"


class TestSheetTable:
    def test_3行目のヘッダを採用する(self) -> None:
        values = [
            ["んh", "CHECK2", "ASIN_SELL"],
            ["", "", "ASIN"],
            ["0", "1", ""],
            ["", "", "B0CCX6ZXRV"],
        ]
        table = SheetTable(values, header_row=3)

        assert table.headers[2] == "ASIN"

    def test_3行目が空なら2行目のヘッダで補う(self) -> None:
        values = [
            ["", "", ""],
            ["", "", "ASIN", "商品画像"],
            ["", "", "", ""],
            ["", "", "B0CCX6ZXRV"],
        ]
        table = SheetTable(values, header_row=3)

        assert table.headers[2] == "ASIN"
        assert table.headers[3] == "商品画像"

    def test_データ行はヘッダ行の次から始まる(self) -> None:
        values = [["a"], ["b"], ["c"], ["d1"], ["d2"]]
        table = SheetTable(values, header_row=3)

        assert table.data_rows == [["d1"], ["d2"]]
        assert table.row_number(0) == 4
        assert table.row_number(1) == 5

    def test_ヘッダより下に行が無ければ空(self) -> None:
        table = SheetTable([["a"], ["b"], ["c"]], header_row=3)

        assert table.data_rows == []


class FakeWorksheet:
    def __init__(self, values: list[list]) -> None:
        self.values = values
        self.render_options: list[object] = []

    def get_values(self, *args, **kwargs) -> list[list]:
        self.render_options.append(kwargs.get("value_render_option"))
        return self.values


class FakeSpreadsheet:
    def __init__(self, worksheet: FakeWorksheet) -> None:
        self.worksheet_obj = worksheet

    def worksheet(self, name: str) -> FakeWorksheet:
        return self.worksheet_obj


class TestReadTableRendering:
    def test_数式のまま読み取る(self) -> None:
        from src.infrastructure.sheet_repository import FORMULA_RENDER_OPTION, GoogleSheetRepository

        worksheet = FakeWorksheet([[], [], ["", "", "ASIN"], ["", "", "B0CCX6ZXRV"]])
        repository = GoogleSheetRepository.__new__(GoogleSheetRepository)
        repository.spreadsheet = FakeSpreadsheet(worksheet)

        repository.read_table("優先")

        assert worksheet.render_options == [FORMULA_RENDER_OPTION]

    def test_画像数式が入った列は空欄とみなさない(self) -> None:
        from src.infrastructure.column_mapper import ColumnMapper
        from src.usecases.row_update_planner import RowUpdatePlanner

        headers = ["", "", "ASIN", "", "", "商品画像", "商品名"]
        row = ["", "", "B0CCX6ZXRV", "", "", '=HYPERLINK("u", IMAGE("i"))', "商品名"]
        planner = RowUpdatePlanner(ColumnMapper(headers), overwrite=False)

        assert planner.needs_fetch(row) is False


class FakeTitledWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title


class FakeBatchGetSpreadsheet:
    def __init__(self, titles: list[str], value_ranges: list[dict]) -> None:
        self.titles = titles
        self.value_ranges = value_ranges
        self.calls: list[tuple[list[str], dict | None]] = []

    def worksheets(self) -> list[FakeTitledWorksheet]:
        return [FakeTitledWorksheet(title) for title in self.titles]

    def values_batch_get(self, ranges: list[str], params: dict | None = None) -> dict:
        self.calls.append((ranges, params))
        return {"valueRanges": self.value_ranges}


class TestReadAllValues:
    def test_タブ数によらず一括取得は1回のリクエストになる(self) -> None:
        from src.infrastructure.sheet_repository import FORMULA_RENDER_OPTION, GoogleSheetRepository

        spreadsheet = FakeBatchGetSpreadsheet(
            titles=["優先", "候補", "自動調査"],
            value_ranges=[
                {"values": [["a"]]},
                {"values": [["b"]]},
                {},  # 空タブは values キー自体が無い
            ],
        )
        repository = GoogleSheetRepository.__new__(GoogleSheetRepository)
        repository.spreadsheet = spreadsheet

        result = repository.read_all_values()

        assert len(spreadsheet.calls) == 1
        ranges, params = spreadsheet.calls[0]
        assert ranges == ["'優先'", "'候補'", "'自動調査'"]
        assert params == {"valueRenderOption": FORMULA_RENDER_OPTION}
        assert result == {"優先": [["a"]], "候補": [["b"]], "自動調査": []}


class TestPlanColumnInsert:
    def test_列コードが無ければ挿入位置を返す(self) -> None:
        from src.usecases.rival_research import plan_column_insert

        codes = ["", "CHECK2", "ASIN_SELL", "IMAGE", "TITLE_SELL", "TITLE_BUY"]

        assert plan_column_insert(codes, after_code="TITLE_SELL", new_code="RIVAL_RANK") == 5

    def test_既に列コードがあれば挿入しない(self) -> None:
        from src.usecases.rival_research import plan_column_insert

        codes = ["ASIN_SELL", "TITLE_SELL", "RIVAL_RANK", "TITLE_BUY"]

        assert plan_column_insert(codes, after_code="TITLE_SELL", new_code="RIVAL_RANK") is None

    def test_基準の列コードが無ければ例外(self) -> None:
        import pytest

        from src.usecases.rival_research import plan_column_insert

        with pytest.raises(ValueError, match="TITLE_SELL"):
            plan_column_insert(["ASIN_SELL"], after_code="TITLE_SELL", new_code="RIVAL_RANK")
