from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import SheetTable
from src.usecases.select_supplier_targets import SupplierTarget, select_targets

IMAGE_A = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
IMAGE_B = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CQ245KMT", IMAGE("https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"))'


def build_values(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "ASIN_SELL", "", "", "IMAGE", "LINK_LOWEST"]
    header2 = ["", "", "ASIN", "", "", "画像URL", "購入先"]
    header3 = ["", "", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


class TestSelectTargets:
    def test_購入先が空で画像がある行を選ぶ(self) -> None:
        values = build_values([["", "", "B0CCX6ZXRV", "", "", IMAGE_A, ""]])
        table = SheetTable(values)
        targets = select_targets(table, ColumnCodes(values))
        assert targets == [
            SupplierTarget(
                row_number=4,
                asin="B0CCX6ZXRV",
                image_url="https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg",
            )
        ]

    def test_購入先が既に入っている行は除外する(self) -> None:
        values = build_values([
            ["", "", "B0CCX6ZXRV", "", "", IMAGE_A, "https://detail.1688.com/offer/1.html"],
        ])
        assert select_targets(SheetTable(values), ColumnCodes(values)) == []

    def test_画像が無い行は除外する(self) -> None:
        values = build_values([["", "", "B0CCX6ZXRV", "", "", "", ""]])
        assert select_targets(SheetTable(values), ColumnCodes(values)) == []

    def test_上限で打ち切る(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", IMAGE_B, ""] for i in range(5)]
        values = build_values(rows)
        targets = select_targets(SheetTable(values), ColumnCodes(values), limit=2)
        assert len(targets) == 2
        assert [t.row_number for t in targets] == [4, 5]

    def test_ASINが空の行も画像があれば選ぶ(self) -> None:
        values = build_values([["", "", "", "", "", IMAGE_A, ""]])
        targets = select_targets(SheetTable(values), ColumnCodes(values))
        assert targets[0].asin == ""
