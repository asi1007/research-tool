from __future__ import annotations

import json

import pytest

from find_supplier import (
    REQUIRED_WRITE_CODES,
    HighlightError,
    LinkLowestState,
    build_targets_result,
    describe_candidates,
    drop_occupied_columns,
    header_row_error,
    link_lowest_state,
    missing_write_codes,
    parse_candidates_payload,
    write_and_highlight,
)
from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import DEFAULT_HEADER_ROW, SheetTable


class TestMissingWriteCodes:
    def test_全コードが揃っていれば空リスト(self) -> None:
        code_row = list(REQUIRED_WRITE_CODES)
        values = [code_row]
        assert missing_write_codes(ColumnCodes(values)) == []

    def test_2つ欠けていればその2つをREQUIRED_WRITE_CODESの順で返す(self) -> None:
        missing_codes = {"PRICE_LOWEST", "CURRENCY_BUY_OTHER1"}
        code_row = [code for code in REQUIRED_WRITE_CODES if code not in missing_codes]
        values = [code_row]
        assert missing_write_codes(ColumnCodes(values)) == [
            "PRICE_LOWEST",
            "CURRENCY_BUY_OTHER1",
        ]


class TestLinkLowestState:
    def test_対象行のLINK_LOWESTが空なら書き込んでよい(self) -> None:
        values = [[], [], [], ["", "", ""]]
        assert link_lowest_state(values, row_number=4, link_index=2) is LinkLowestState.BLANK

    def test_対象行のLINK_LOWESTに値があれば書き込んではいけない(self) -> None:
        values = [[], [], [], ["", "", "https://detail.1688.com/offer/1.html"]]
        assert link_lowest_state(values, row_number=4, link_index=2) is LinkLowestState.OCCUPIED

    def test_対象行のLINK_LOWESTが空白文字のみなら空とみなす(self) -> None:
        values = [[], [], [], ["", "", "  \n"]]
        assert link_lowest_state(values, row_number=4, link_index=2) is LinkLowestState.BLANK

    def test_対象行がvaluesの範囲外なら書き込んではいけない(self) -> None:
        values = [[], [], [], ["", "", ""]]
        assert link_lowest_state(values, row_number=99, link_index=2) is LinkLowestState.ROW_NOT_FOUND

    def test_行はあるが列番号に長さが足りない場合も範囲外扱い(self) -> None:
        values = [[], [], [], ["", ""]]
        assert link_lowest_state(values, row_number=4, link_index=2) is LinkLowestState.ROW_NOT_FOUND


class TestHeaderRowError:
    def test_ヘッダー行より後ならNone(self) -> None:
        assert header_row_error(DEFAULT_HEADER_ROW + 1, DEFAULT_HEADER_ROW) is None

    def test_ヘッダー行そのものはエラー(self) -> None:
        assert header_row_error(DEFAULT_HEADER_ROW, DEFAULT_HEADER_ROW) is not None

    def test_ヘッダーより前もエラー(self) -> None:
        assert header_row_error(1, DEFAULT_HEADER_ROW) is not None
        assert header_row_error(2, DEFAULT_HEADER_ROW) is not None


class TestParseCandidatesPayload:
    def test_リストならそのまま返す(self) -> None:
        assert parse_candidates_payload(json.dumps([{"offerId": "1"}])) == [{"offerId": "1"}]

    def test_空リストは正常系として返す(self) -> None:
        assert parse_candidates_payload(json.dumps([])) == []

    def test_二重エンコードされた文字列は例外(self) -> None:
        double_encoded = json.dumps(json.dumps([{"offerId": "1"}]))
        with pytest.raises(ValueError):
            parse_candidates_payload(double_encoded)

    def test_辞書は例外(self) -> None:
        with pytest.raises(ValueError):
            parse_candidates_payload(json.dumps({"offerId": "1"}))


class TestDropOccupiedColumns:
    def test_値が入っている列だけ除外する(self) -> None:
        codes = ColumnCodes([list(REQUIRED_WRITE_CODES)])
        values = [
            list(REQUIRED_WRITE_CODES),
            [], [], [],
            ["", "", "", "https://example.com/other1-existing", "", "", "12.5", "", "", "", ""],
        ]
        updates = {
            0: "url0", 1: "=C5*24", 2: 0.03,
            3: "url-guess", 4: "=G5*24", 5: "CHY", 6: 0.05,
        }
        kept, skipped = drop_occupied_columns(values, 5, updates, codes)
        assert kept == {0: "url0", 1: "=C5*24", 2: 0.03, 4: "=G5*24", 5: "CHY"}
        assert skipped == {
            "LINK_BUY_OTHER1": "https://example.com/other1-existing",
            "LOCALPRICE_BUY_OTHER1": "12.5",
        }

    def test_何も入っていなければ全て残す(self) -> None:
        codes = ColumnCodes([list(REQUIRED_WRITE_CODES)])
        values = [list(REQUIRED_WRITE_CODES), [], [], [], ["", "", ""]]
        updates = {0: "url0", 1: "=C5*24"}
        kept, skipped = drop_occupied_columns(values, 5, updates, codes)
        assert kept == updates
        assert skipped == {}

    def test_全列が既に埋まっていれば全て除外する(self) -> None:
        codes = ColumnCodes([list(REQUIRED_WRITE_CODES)])
        values = [
            list(REQUIRED_WRITE_CODES), [], [], [],
            ["existing-url", "existing-price"],
        ]
        updates = {0: "url-guess", 1: "=B5*24"}
        kept, skipped = drop_occupied_columns(values, 5, updates, codes)
        assert kept == {}
        assert skipped == {"LINK_LOWEST": "existing-url", "PRICE_LOWEST": "existing-price"}


class TestDescribeCandidates:
    def test_スクレイピングしたフィールドを辞書化する(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("620082943880"),
            title="强力磁铁",
            company="雄尊磁铁厂",
            province="浙江",
            local_price=0.03,
            quantity=1,
        )
        assert describe_candidates([candidate]) == [
            {
                "offer_id": "620082943880",
                "title": "强力磁铁",
                "company": "雄尊磁铁厂",
                "province": "浙江",
                "local_price": 0.03,
                "quantity": 1,
            }
        ]

    def test_数量が1以外でもログへ含める(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("853573456382"),
            title="现货钕铁硼强力圆形10*2磁铁 300颗/袋",
            company="丽嘉磁业工厂",
            province="广东",
            local_price=0.01,
            quantity=300,
        )
        assert describe_candidates([candidate])[0]["quantity"] == 300

    def test_空リストなら空リスト(self) -> None:
        assert describe_candidates([]) == []


class FakeRepository:
    def __init__(self) -> None:
        self.applied: dict[int, dict[int, object]] = {}

    def apply_updates(self, sheet_name: str, updates: dict[int, dict[int, object]]) -> int:
        self.applied = updates
        return sum(len(columns) for columns in updates.values())


class RaisingWorksheet:
    def batch_format(self, formats: list[dict]) -> None:
        raise RuntimeError("boom")


class RecordingWorksheet:
    def __init__(self) -> None:
        self.received: list[dict] = []

    def batch_format(self, formats: list[dict]) -> None:
        self.received = formats


class TestWriteAndHighlight:
    def test_成功時は書き込み件数を返す(self) -> None:
        codes = ColumnCodes([list(REQUIRED_WRITE_CODES)])
        repository = FakeRepository()
        worksheet = RecordingWorksheet()
        written = write_and_highlight(
            repository, worksheet, "sheet", 5, {0: "url", 1: "=C5*24"}, codes
        )
        assert written == 2
        assert repository.applied == {5: {0: "url", 1: "=C5*24"}}
        assert len(worksheet.received) == 2

    def test_背景色設定が失敗しても値は書き込まれ列名付きで例外化する(self) -> None:
        codes = ColumnCodes([list(REQUIRED_WRITE_CODES)])
        repository = FakeRepository()
        with pytest.raises(HighlightError) as excinfo:
            write_and_highlight(
                repository, RaisingWorksheet(), "sheet", 5, {0: "url", 1: "=C5*24"}, codes
            )
        assert excinfo.value.row == 5
        assert set(excinfo.value.columns) == {"LINK_LOWEST", "PRICE_LOWEST"}
        assert repository.applied == {5: {0: "url", 1: "=C5*24"}}


class TestBuildTargetsResult:
    def test_列コードが揃っていれば対象行を返す(self) -> None:
        code_row = ["", "", "ASIN_SELL", "", "", "IMAGE", "LINK_LOWEST"]
        header2 = ["", "", "ASIN", "", "", "画像URL", "購入先"]
        header3 = ["", "", "", "", "", "", ""]
        image = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
        data_row = ["", "", "B0CCX6ZXRV", "", "", image, ""]
        values = [code_row, header2, header3, data_row]
        table = SheetTable(values)
        codes = ColumnCodes(values)

        targets, error = build_targets_result(table, codes, limit=10)

        assert error is None
        assert len(targets) == 1
        assert targets[0].row_number == 4

    def test_LINK_LOWESTコードが無ければエラーメッセージを返し対象は空(self) -> None:
        code_row = ["", "", "ASIN_SELL", "", "", "IMAGE"]
        header2 = ["", "", "ASIN", "", "", "画像URL"]
        header3 = ["", "", "", "", "", ""]
        values = [code_row, header2, header3]
        table = SheetTable(values)
        codes = ColumnCodes(values)

        targets, error = build_targets_result(table, codes, limit=10)

        assert targets == []
        assert error is not None
        assert "LINK_LOWEST" in error
