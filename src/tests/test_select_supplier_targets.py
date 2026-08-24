import pytest

from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import SheetTable
from src.usecases.select_supplier_targets import SupplierTarget, select_targets

IMAGE_A = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
IMAGE_B = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CQ245KMT", IMAGE("https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"))'


def build_values(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "ASIN_SELL", "TITLE_SELL", "", "IMAGE", "LINK_LOWEST"]
    header2 = ["", "", "ASIN", "商品名", "", "画像URL", "購入先"]
    header3 = ["", "", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


def build_values_without_title(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "ASIN_SELL", "", "", "IMAGE", "LINK_LOWEST"]
    header2 = ["", "", "ASIN", "", "", "画像URL", "購入先"]
    header3 = ["", "", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


def build_values_without_link_lowest(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "ASIN_SELL", "", "", "IMAGE"]
    header2 = ["", "", "ASIN", "", "", "画像URL"]
    header3 = ["", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


def build_values_without_image(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "ASIN_SELL", "", "", "LINK_LOWEST"]
    header2 = ["", "", "ASIN", "", "", "購入先"]
    header3 = ["", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


def build_values_without_asin(data_rows: list[list]) -> list[list]:
    code_row = ["", "", "", "", "", "IMAGE", "LINK_LOWEST"]
    header2 = ["", "", "", "", "", "画像URL", "購入先"]
    header3 = ["", "", "", "", "", "", ""]
    return [code_row, header2, header3, *data_rows]


class TestSelectTargets:
    def test_購入先が空で画像がある行を選ぶ(self) -> None:
        values = build_values([["", "", "B0CCX6ZXRV", "強力マグネット50個セット", "", IMAGE_A, ""]])
        table = SheetTable(values)
        targets = select_targets(table, ColumnCodes(values))
        assert targets == [
            SupplierTarget(
                row_number=4,
                asin="B0CCX6ZXRV",
                title="強力マグネット50個セット",
                image_url="https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg",
            )
        ]

    def test_TITLE_SELLコードが無くても例外にならない(self) -> None:
        values = build_values_without_title([["", "", "B0CCX6ZXRV", "", "", IMAGE_A, ""]])
        targets = select_targets(SheetTable(values), ColumnCodes(values))
        assert len(targets) == 1
        assert targets[0].title == ""

    def test_商品名セルが空なら空文字にする(self) -> None:
        values = build_values([["", "", "B0CCX6ZXRV", "", "", IMAGE_A, ""]])
        targets = select_targets(SheetTable(values), ColumnCodes(values))
        assert targets[0].title == ""

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

    def test_LINK_LOWESTコードが無い場合ValueError(self) -> None:
        values = build_values_without_link_lowest([
            ["", "", "B0CCX6ZXRV", "", "", IMAGE_A],
            ["", "", "B0CQ245KMT", "", "", IMAGE_B],
        ])
        with pytest.raises(ValueError, match="LINK_LOWEST"):
            select_targets(SheetTable(values), ColumnCodes(values))

    def test_IMAGEコードが無い場合ValueError(self) -> None:
        values = build_values_without_image([["", "", "B0CCX6ZXRV", "", "", "https://detail.1688.com/offer/1.html"]])
        with pytest.raises(ValueError, match="IMAGE"):
            select_targets(SheetTable(values), ColumnCodes(values))

    def test_ASINコードが無くても例外にならない(self) -> None:
        values = build_values_without_asin([["", "", "", "", "", IMAGE_A, ""]])
        targets = select_targets(SheetTable(values), ColumnCodes(values))
        assert len(targets) == 1
        assert targets[0].asin == ""
