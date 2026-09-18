from src.domain.value_objects.supplier_skips import SupplierSkips
from src.usecases.find_supplier_auto import (
    EMPTY_CANDIDATES_REASON,
    SKIP_PREFIX,
    build_decision_prompt,
    parse_decision,
    looks_blocked,
    parse_skips,
    pick_batch,
    skip_reason_for,
)
from src.usecases.select_supplier_targets import SupplierTarget


def _target(asin: str, row: int = 4) -> SupplierTarget:
    return SupplierTarget(row_number=row, asin=asin, title=f"商品{asin}", image_url=f"https://img/{asin}.jpg")


class TestPickBatch:
    def test_最初に対象がある安いタブから取る(self) -> None:
        by_sheet = {"自動調査500円以下": [], "自動調査500円-700円": [_target("B000000001"), _target("B000000002")]}

        sheet, batch = pick_batch(by_sheet, SupplierSkips(), limit=5)

        assert sheet == "自動調査500円-700円"
        assert [t.asin for t in batch] == ["B000000001", "B000000002"]

    def test_件数の上限で切る(self) -> None:
        by_sheet = {"A": [_target(f"B00000000{i}") for i in range(1, 6)]}

        _, batch = pick_batch(by_sheet, SupplierSkips(), limit=2)

        assert len(batch) == 2

    def test_飛ばすと決めたASINは取らない(self) -> None:
        skips = SupplierSkips({"B000000001": "画像検索で外れた"})
        by_sheet = {"A": [_target("B000000001"), _target("B000000002")]}

        _, batch = pick_batch(by_sheet, skips, limit=5)

        assert [t.asin for t in batch] == ["B000000002"]

    def test_対象が無ければNone(self) -> None:
        assert pick_batch({"A": []}, SupplierSkips(), limit=5) == (None, [])


class TestParseSkips:
    def test_飛ばした行を理由つきで拾う(self) -> None:
        text = f"書き込み2件\n{SKIP_PREFIX} B000000001 画像検索で別カテゴリが返った\n{SKIP_PREFIX} B000000002 1688に同款なし"

        assert parse_skips(text) == {"B000000001": "画像検索で別カテゴリが返った", "B000000002": "1688に同款なし"}

    def test_理由が無くても拾う(self) -> None:
        assert parse_skips(f"{SKIP_PREFIX} B000000001") == {"B000000001": ""}

    def test_ASINでない行は無視する(self) -> None:
        assert parse_skips(f"{SKIP_PREFIX} これはASINではない") == {}


class TestSupplierSkips:
    def test_追加して読み戻せる(self, tmp_path) -> None:
        path = tmp_path / "skips.json"
        skips = SupplierSkips.load(path)
        skips.add("B000000001", "画像検索で外れた")
        skips.save(path)

        assert SupplierSkips.load(path).contains("B000000001") is True

    def test_ファイルが無ければ空(self, tmp_path) -> None:
        assert SupplierSkips.load(tmp_path / "missing.json").contains("B000000001") is False


class FakeRepository:
    def __init__(self, values: dict[str, list[list]]) -> None:
        self.values = values

    def sheet_titles(self) -> list[str]:
        return list(self.values)

    def read_values(self, sheet_name: str) -> list[list]:
        return self.values[sheet_name]


CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "IMAGE", "TITLE_SELL", "LINK_LOWEST"]
LABEL_ROW = ["", "", "ASIN", "画像", "商品名", "購入先"]
UNIT_ROW = ["", "", "", "", "", ""]


def _sheet(rows: list[list]) -> list[list]:
    return [CODE_ROW, LABEL_ROW, UNIT_ROW, *rows]


SCRAPED = {
    "candidates": [
        {
            "offer_id": "123456789012",
            "title": "汽车挡风玻璃擦清洁刷",
            "company": "義烏の会社",
            "province": "浙江",
            "card_price": 7.6,
            "variants": [{"spec": "1套+4个布套", "price": 9.46}, {"spec": "1套+1个布套", "price": 7.07}],
        }
    ]
}


class TestRun:
    def _args(self, **overrides):
        import argparse

        base = {"limit": 2, "sheet": None, "timeout": 60, "variant_offers": 2, "dry_run": False, "debug": False}
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_対象が無ければclaudeを起動しない(self, monkeypatch) -> None:
        import find_supplier_auto as cli

        called = {"run": False}
        monkeypatch.setattr(cli, "run_claude", lambda *a, **k: called.update(run=True) or (0, ""))
        repository = FakeRepository({"自動調査1000円以下": _sheet([["", "", "B000000001", "=IMAGE(\"x\")", "商品", "https://detail.1688.com/offer/1.html"]])})

        assert cli.run(self._args(), repository=repository) == 0
        assert called["run"] is False

    def test_キャプチャが出たら2を返す(self, monkeypatch, tmp_path) -> None:
        import find_supplier_auto as cli
        from src.infrastructure.alibaba_scraper import CaptchaError

        def 止まる(*args, **kwargs):
            raise CaptchaError("1688 がキャプチャを出しました")

        monkeypatch.setattr(cli, "SKIPS_PATH", tmp_path / "skips.json")
        monkeypatch.setattr(cli, "download_image", lambda target, directory: tmp_path / "x.jpg")
        monkeypatch.setattr(cli, "collect", 止まる)
        repository = FakeRepository({"自動調査1000円以下": _sheet([["", "", "B000000001", '=HYPERLINK("u", IMAGE("https://img/1.jpg"))', "商品", ""]])})

        assert cli.run(self._args(), repository=repository) == 2

    def test_飛ばしたASINを記録して次回は選ばない(self, monkeypatch, tmp_path) -> None:
        import find_supplier_auto as cli
        from src.domain.value_objects.supplier_skips import SupplierSkips

        path = tmp_path / "skips.json"
        monkeypatch.setattr(cli, "SKIPS_PATH", path)
        monkeypatch.setattr(cli, "download_image", lambda target, directory: tmp_path / "x.jpg")
        monkeypatch.setattr(cli, "collect", lambda image_path, variant_offers=2: SCRAPED)
        monkeypatch.setattr(cli, "run_claude", lambda *a, **k: (0, f"{SKIP_PREFIX} B000000001 別カテゴリが返った"))
        repository = FakeRepository({"自動調査1000円以下": _sheet([["", "", "B000000001", '=HYPERLINK("u", IMAGE("https://img/1.jpg"))', "商品", ""]])})

        assert cli.run(self._args(), repository=repository) == 0
        assert SupplierSkips.load(path).contains("B000000001") is True

    def test_全件が空なら飛ばす記録を残さず3を返す(self, monkeypatch, tmp_path) -> None:
        import find_supplier_auto as cli
        from src.domain.value_objects.supplier_skips import SupplierSkips

        path = tmp_path / "skips.json"
        monkeypatch.setattr(cli, "SKIPS_PATH", path)
        monkeypatch.setattr(cli, "download_image", lambda target, directory: tmp_path / "x.jpg")
        monkeypatch.setattr(cli, "collect", lambda image_path, variant_offers=2: {"candidates": []})
        repository = FakeRepository({"自動調査1000円以下": _sheet([["", "", "B000000001", '=HYPERLINK("u", IMAGE("https://img/1.jpg"))', "商品", ""]])})

        assert cli.run(self._args(), repository=repository) == 3
        assert SupplierSkips.load(path).contains("B000000001") is False

    def test_選ばれた候補を書き込む(self, monkeypatch, tmp_path) -> None:
        import find_supplier_auto as cli

        written: dict = {}
        monkeypatch.setattr(cli, "SKIPS_PATH", tmp_path / "skips.json")
        monkeypatch.setattr(cli, "download_image", lambda target, directory: tmp_path / "x.jpg")
        monkeypatch.setattr(cli, "collect", lambda image_path, variant_offers=2: SCRAPED)
        monkeypatch.setattr(
            cli,
            "run_claude",
            lambda *a, **k: (0, '[{"offerId": "123456789012", "spec": "1套+4个布套", "price": 9.46, "quantity": 1}]'),
        )
        monkeypatch.setattr(
            cli,
            "write_candidates",
            lambda sheet, target, decided, repository: written.update(asin=target.asin, decided=decided) or 4,
        )
        repository = FakeRepository({"自動調査1000円以下": _sheet([["", "", "B000000001", '=HYPERLINK("u", IMAGE("https://img/1.jpg"))', "商品", ""]])})

        assert cli.run(self._args(), repository=repository) == 0
        assert written["asin"] == "B000000001"
        assert written["decided"][0]["offerId"] == "123456789012"


class TestBuildDecisionPrompt:
    def test_Amazon側の商品名と候補の規格を渡す(self) -> None:
        prompt = build_decision_prompt(_target("B000000001"), SCRAPED)

        assert "商品B000000001" in prompt
        assert "123456789012" in prompt
        assert "1套+4个布套" in prompt

    def test_出力の形と飛ばし方を指示する(self) -> None:
        prompt = build_decision_prompt(_target("B000000001"), SCRAPED)

        assert "offerId" in prompt and "quantity" in prompt
        assert SKIP_PREFIX in prompt

    def test_ブランド品と生き物は書かずに飛ばすと指示する(self) -> None:
        prompt = build_decision_prompt(_target("B000000001"), SCRAPED)
        assert "ブランド品" in prompt
        assert "生き物" in prompt

    def test_ブラウザを使わないと明記する(self) -> None:
        # 候補は playwright が取り終えている。claude はもう検索しない
        assert "ブラウザ" in build_decision_prompt(_target("B000000001"), SCRAPED)


class TestSkipReasonFor:
    def test_候補が空なら理由を返す(self) -> None:
        assert skip_reason_for({"candidates": []}) == EMPTY_CANDIDATES_REASON

    def test_候補があればNone(self) -> None:
        assert skip_reason_for(SCRAPED) is None


class TestLooksBlocked:
    def test_候補が1件も出ない実行は遮断として扱う(self) -> None:
        assert looks_blocked(empty_count=3, found_count=0) is True

    def test_他の行で候補が出ていれば同款が無いだけ(self) -> None:
        assert looks_blocked(empty_count=2, found_count=1) is False

    def test_空が無ければ遮断でない(self) -> None:
        assert looks_blocked(empty_count=0, found_count=0) is False


class TestParseDecision:
    def test_候補のJSONを取り出す(self) -> None:
        text = 'この候補が一致します\n```json\n[{"offerId": "123456789012", "spec": "1套+4个布套", "price": 9.46, "quantity": 1}]\n```'

        candidates, skip = parse_decision(text)

        assert skip is None
        assert candidates[0]["offerId"] == "123456789012"

    def test_飛ばす指示を取り出す(self) -> None:
        candidates, skip = parse_decision(f"{SKIP_PREFIX} B000000001 別カテゴリしか返っていない")

        assert candidates == []
        assert skip == "別カテゴリしか返っていない"

    def test_どちらも無ければ飛ばす扱い(self) -> None:
        candidates, skip = parse_decision("判断できませんでした")

        assert candidates == []
        assert skip is not None
