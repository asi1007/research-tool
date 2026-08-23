from src.domain.entities.product_info import ProductInfo
from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin
from src.infrastructure.sheet_repository import SheetTable
from src.infrastructure.shipping_calculator import InternationalShippingCalculator
from src.usecases.bulk_fetch_products import BulkFetchProductsUseCase

HEADER_ROWS = [
    ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "画像URL", "商品名"],
    ["", "", "ASIN", "GTIN", "", "画像URL", "商品名"],
    ["", "", "", "JAN/EAN", "UPC", "", ""],
]


class FakeRepository:
    def __init__(self, data_rows: list[list]) -> None:
        self.table = SheetTable(HEADER_ROWS + data_rows, header_row=3)
        self.applied: dict[str, dict] = {}

    def read_table(self, sheet_name: str, header_row: int = 3) -> SheetTable:
        return self.table

    def apply_updates(self, sheet_name: str, updates: dict) -> int:
        self.applied[sheet_name] = updates
        return sum(len(columns) for columns in updates.values())


class FakeFetcher:
    def __init__(self, error_asins: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.error_asins = error_asins or set()

    def fetch(self, asin: Asin) -> ProductInfo:
        self.calls.append(str(asin))
        if str(asin) in self.error_asins:
            raise RuntimeError("API failure")
        return ProductInfo(
            asin=asin, title=f"商品-{asin}", image_url="71a.jpg", size=ProductSize(200, 100, 30)
        )


def _usecase(repository, fetcher, **kwargs) -> BulkFetchProductsUseCase:
    return BulkFetchProductsUseCase(
        repository=repository,
        fetcher=fetcher,
        shipping_calculator=InternationalShippingCalculator(7.0, 21.0),
        interval_seconds=0,
        **kwargs,
    )


class TestExecute:
    def test_ASINとURLの両方を処理する(self) -> None:
        rows = [
            ["", "", "B0CCX6ZXRV", "", "", "", ""],
            ["", "", "https://www.amazon.co.jp/x/dp/B0H455Y954/ref=sr_1_18?th=1", "", "", "", ""],
        ]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).execute("テスト")

        assert fetcher.calls == ["B0CCX6ZXRV", "B0H455Y954"]
        assert result.fetched == 2

    def test_ASINとして解釈できない行は数えてスキップする(self) -> None:
        rows = [["", "", "掃除グッズ　水垢とか", "", "", "", ""]]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).execute("テスト")

        assert fetcher.calls == []
        assert result.invalid_asin == 1

    def test_空行はスキップして数えない(self) -> None:
        rows = [["", "", "", "", "", "", ""]]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).execute("テスト")

        assert result.invalid_asin == 0
        assert result.fetched == 0

    def test_既に埋まっている行はAPIを呼ばない(self) -> None:
        rows = [["", "", "B0CCX6ZXRV", "", "", "既存画像", "既存商品名"]]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).execute("テスト")

        assert fetcher.calls == []
        assert result.already_filled == 1

    def test_上書きモードでは埋まっている行も取得する(self) -> None:
        rows = [["", "", "B0CCX6ZXRV", "", "", "既存画像", "既存商品名"]]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher, overwrite=True).execute("テスト")

        assert fetcher.calls == ["B0CCX6ZXRV"]
        assert result.already_filled == 0

    def test_dry_runでは書き込まない(self) -> None:
        rows = [["", "", "B0CCX6ZXRV", "", "", "", ""]]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher, dry_run=True).execute("テスト")

        assert repository.applied == {}
        assert result.updated_cells == 2

    def test_書き込みは正しい行番号に対応する(self) -> None:
        rows = [
            ["", "", "", "", "", "", ""],
            ["", "", "B0CCX6ZXRV", "", "", "", ""],
        ]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        _usecase(repository, fetcher).execute("テスト")

        assert list(repository.applied["テスト"]) == [5]

    def test_limitで取得件数を制限する(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", "", ""] for i in range(5)]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).execute("テスト", limit=2)

        assert len(fetcher.calls) == 2
        assert result.fetched == 2

    def test_1件失敗しても残りを処理する(self) -> None:
        rows = [
            ["", "", "B0CCX6ZXR1", "", "", "", ""],
            ["", "", "B0CCX6ZXR2", "", "", "", ""],
        ]
        repository = FakeRepository(rows)
        fetcher = FakeFetcher(error_asins={"B0CCX6ZXR1"})

        result = _usecase(repository, fetcher).execute("テスト")

        assert result.failed == ["B0CCX6ZXR1"]
        assert result.fetched == 1
        assert list(repository.applied["テスト"]) == [5]

    def test_ASIN列が無いシートは何もしない(self) -> None:
        repository = FakeRepository([])
        repository.table = SheetTable([["a"], ["b"], ["商品名"], ["x"]], header_row=3)
        fetcher = FakeFetcher()

        result = _usecase(repository, fetcher).execute("プロンプト")

        assert fetcher.calls == []
        assert result.fetched == 0


class TestCountTargets:
    def test_APIを呼ばずに対象件数を数える(self) -> None:
        rows = [
            ["", "", "B0CCX6ZXRV", "", "", "", ""],
            ["", "", "掃除グッズ", "", "", "", ""],
            ["", "", "B0CQ245KMT", "", "", "既存画像", "既存商品名"],
            ["", "", "", "", "", "", ""],
        ]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher).count_targets("テスト")

        assert fetcher.calls == []
        assert result.total_rows == 4
        assert result.fetched == 1
        assert result.invalid_asin == 1
        assert result.already_filled == 1


class TestCheckpoint:
    def test_一定件数ごとに途中保存する(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", "", ""] for i in range(5)]
        repository, fetcher = FakeRepository(rows), FakeFetcher()
        repository.apply_history = []

        original = repository.apply_updates

        def recording(sheet_name, updates):
            repository.apply_history.append(sorted(updates))
            return original(sheet_name, updates)

        repository.apply_updates = recording

        _usecase(repository, fetcher, checkpoint_size=2).execute("テスト")

        assert repository.apply_history == [[4, 5], [6, 7], [8]]

    def test_途中保存した行は再度書き込まない(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", "", ""] for i in range(3)]
        repository, fetcher = FakeRepository(rows), FakeFetcher()
        written: list[int] = []

        original = repository.apply_updates

        def recording(sheet_name, updates):
            written.extend(updates)
            return original(sheet_name, updates)

        repository.apply_updates = recording

        _usecase(repository, fetcher, checkpoint_size=2).execute("テスト")

        assert sorted(written) == [4, 5, 6]
        assert len(written) == len(set(written))

    def test_途中保存の件数は書き込みセル数に積み上がる(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", "", ""] for i in range(3)]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher, checkpoint_size=2).execute("テスト")

        assert result.updated_cells == 6

    def test_dry_runでは途中保存しない(self) -> None:
        rows = [["", "", f"B0CCX6ZXR{i}", "", "", "", ""] for i in range(3)]
        repository, fetcher = FakeRepository(rows), FakeFetcher()

        result = _usecase(repository, fetcher, dry_run=True, checkpoint_size=2).execute("テスト")

        assert repository.applied == {}
        assert result.updated_cells == 6
