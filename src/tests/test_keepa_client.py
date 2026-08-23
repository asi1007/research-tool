from src.domain.value_objects.asin import Asin
from src.infrastructure.keepa_client import KeepaClient


class TestKeepaExtract:
    def test_商品情報を抽出する(self) -> None:
        raw = {
            "asin": "B0CCX6ZXRV",
            "title": "テスト商品",
            "imagesCSV": "71abc.jpg,72def.jpg",
            "packageLength": 200,
            "packageWidth": 100,
            "packageHeight": 30,
            "packageWeight": 150,
            "monthlySold": 42,
            "csv": {18: [100, 749]},
        }

        info = KeepaClient.extract(Asin("B0CCX6ZXRV"), raw)

        assert info.title == "テスト商品"
        assert info.image_url == "71abc.jpg"
        assert info.size.length_mm == 200
        assert info.weight_grams == 150
        assert info.monthly_sold == 42
        assert info.buy_box_price == 749

    def test_カート価格はcsv18を優先しcsv1へフォールバックする(self) -> None:
        raw = {"asin": "X", "csv": {18: [100, -1], 1: [100, 680]}}
        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 680

    def test_価格が全て無効ならゼロを返す(self) -> None:
        raw = {"asin": "X", "csv": {18: [100, -1], 1: [100, -1], 0: [100, -1]}}
        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 0

    def test_発売日はKeepa分数から変換する(self) -> None:
        raw = {"asin": "X", "releaseDate": 6349680}
        assert KeepaClient.extract(Asin("B000000001"), raw).release_date == "2023-01-27"

    def test_発売日が無効ならpublicationDateのYYYYMMDDを使う(self) -> None:
        raw = {"asin": "X", "releaseDate": -1, "publicationDate": 20190523}
        assert KeepaClient.extract(Asin("B000000001"), raw).release_date == "2019-05-23"

    def test_発売日が取得できなければ空文字を返す(self) -> None:
        raw = {"asin": "X", "releaseDate": 0, "publicationDate": -1}
        assert KeepaClient.extract(Asin("B000000001"), raw).release_date == ""

    def test_画像が無ければ空文字を返す(self) -> None:
        assert KeepaClient.extract(Asin("B000000001"), {"asin": "X"}).image_url == ""


class TestKeepaBuyBoxPriceFromStats:
    def test_statsのカート価格を最優先で使う(self) -> None:
        raw = {"asin": "X", "stats": {"current": [-1] * 19}, "csv": {1: [1, 500]}}
        raw["stats"]["current"][18] = 880

        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 880

    def test_statsのカート価格が無効なら新品価格を使う(self) -> None:
        raw = {"asin": "X", "stats": {"current": [-1] * 19}}
        raw["stats"]["current"][1] = 749

        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 749

    def test_statsが全て無効ならcsvへフォールバックする(self) -> None:
        raw = {"asin": "X", "stats": {"current": [-1] * 19}, "csv": {1: [1, 680]}}

        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 680

    def test_statsが無い場合もcsvから取れる(self) -> None:
        raw = {"asin": "X", "csv": {1: [1, 680]}}

        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 680

    def test_statsのcurrentが短くても落ちない(self) -> None:
        raw = {"asin": "X", "stats": {"current": [500]}, "csv": {}}

        assert KeepaClient.extract(Asin("B000000001"), raw).buy_box_price == 500


class TestKeepaMainImage:
    def test_images配列のMAINバリアントを使う(self) -> None:
        raw = {
            "asin": "X",
            "images": [
                {"l": "71PT01.jpg", "variant": "PT01"},
                {"l": "61MAIN.jpg", "m": "41MAIN.jpg", "variant": "MAIN"},
            ],
        }

        assert KeepaClient.extract(Asin("B000000001"), raw).image_url == "61MAIN.jpg"

    def test_MAINが無ければ先頭の画像を使う(self) -> None:
        raw = {"asin": "X", "images": [{"l": "71PT01.jpg", "variant": "PT01"}]}

        assert KeepaClient.extract(Asin("B000000001"), raw).image_url == "71PT01.jpg"

    def test_lが無ければmを使う(self) -> None:
        raw = {"asin": "X", "images": [{"m": "41MAIN.jpg", "variant": "MAIN"}]}

        assert KeepaClient.extract(Asin("B000000001"), raw).image_url == "41MAIN.jpg"

    def test_旧形式のimagesCSVにフォールバックする(self) -> None:
        raw = {"asin": "X", "imagesCSV": "71old.jpg,81other.jpg"}

        assert KeepaClient.extract(Asin("B000000001"), raw).image_url == "71old.jpg"

    def test_images配列を優先しimagesCSVは使わない(self) -> None:
        raw = {
            "asin": "X",
            "images": [{"l": "61new.jpg", "variant": "MAIN"}],
            "imagesCSV": "71old.jpg",
        }

        assert KeepaClient.extract(Asin("B000000001"), raw).image_url == "61new.jpg"

    def test_imagesが空配列なら空文字(self) -> None:
        assert KeepaClient.extract(Asin("B000000001"), {"asin": "X", "images": []}).image_url == ""
