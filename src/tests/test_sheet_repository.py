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
