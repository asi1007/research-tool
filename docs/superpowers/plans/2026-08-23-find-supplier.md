# /find-supplier 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** リサーチシートの商品画像から 1688 の同款を画像検索し、上位3件の仕入先候補を購入先・他仕入先1・他仕入先2へ自動登録する。

**Architecture:** シートの読み書きは Python（gspread）、1688 の操作は claude-in-chrome の MCP ツールをコマンド手順として記述する。ブラウザから取り出した候補（JSON）を Python に渡して整形・書き込みする2段構成。ブラウザ依存の処理と純粋なデータ整形を分離し、後者だけを pytest で検証する。

**Tech Stack:** Python 3.10+, gspread 6.x, google-auth, pytest, claude-in-chrome MCP

**Spec:** `docs/superpowers/specs/2026-08-23-find-supplier-design.md`

## Global Constraints

- **空白の行だけ埋める。** `LINK_LOWEST`（AG・購入先）が空の行のみ対象。既存の値は上書きしない
- **列は1行目のコードで引く。** ヘッダー名（3行目→2行目）では AR と AW がどちらも `名称` で重複するため使えない
- **URL はクエリ文字列を落とす。** `https://detail.1688.com/offer/{offerId}.html` の形にする
- **通貨は `CHY`**（ユーザー指定。ISO表記の `CNY` ではない）
- **価格（円）は数式で入れる。** `=<現地価格列><行番号>*24`。既存行の AH と同じ形
- **直送送料（`SHIPPING_INTL_OTHER1` / `SHIPPING_INTL_OTHER2`）には書かない**
- **書き込んだセルだけ背景を `#EDEDED`** にする。触らなかったセルの書式は変更しない
- **既定の処理上限は10行**
- `src/` は未追跡で並行セッションが編集中。**`git add` はファイルを個別にパス指定**し、既存ファイルの変更は最小限にとどめる
- テスト実行は `.venv/bin/python -m pytest`

---

### Task 1: OfferId と SupplierCandidate

**Files:**
- Create: `src/domain/value_objects/offer_id.py`
- Create: `src/domain/entities/supplier_candidate.py`
- Test: `src/tests/test_offer_id.py`
- Test: `src/tests/test_supplier_candidate.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `OfferId.parse(raw: object) -> OfferId | None`、`OfferId.value: str`、`OfferId.detail_url -> str`
  - `SupplierCandidate(offer_id: OfferId, title: str, company: str, province: str, local_price: float | None)`、`SupplierCandidate.url -> str`

- [ ] **Step 1: OfferId の失敗するテストを書く**

`src/tests/test_offer_id.py`:

```python
from src.domain.value_objects.offer_id import OfferId


class TestOfferIdParse:
    def test_数字文字列をそのまま受け取る(self) -> None:
        assert OfferId.parse("620082943880") == OfferId("620082943880")

    def test_数値型も受け取る(self) -> None:
        assert OfferId.parse(620082943880) == OfferId("620082943880")

    def test_前後の空白を除去する(self) -> None:
        assert OfferId.parse("  853573456382 \n") == OfferId("853573456382")

    def test_商品URLから抽出する(self) -> None:
        url = "https://detail.1688.com/offer/956382552398.html"
        assert OfferId.parse(url) == OfferId("956382552398")

    def test_クエリ付きURLからも抽出する(self) -> None:
        url = "https://detail.1688.com/offer/674801468466.html?kj_agent_plugin=aliprice&fromkv=xyt"
        assert OfferId.parse(url) == OfferId("674801468466")

    def test_数字以外はNoneを返す(self) -> None:
        assert OfferId.parse("abc") is None

    def test_空はNoneを返す(self) -> None:
        assert OfferId.parse("") is None
        assert OfferId.parse("   ") is None
        assert OfferId.parse(None) is None


class TestOfferIdDetailUrl:
    def test_クエリを含まない商品URLを組み立てる(self) -> None:
        assert OfferId("620082943880").detail_url == "https://detail.1688.com/offer/620082943880.html"
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_offer_id.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.domain.value_objects.offer_id'`）

- [ ] **Step 3: OfferId を実装する**

`src/domain/value_objects/offer_id.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = re.compile(r"^\d+$")
_OFFER_IN_URL = re.compile(r"/offer/(\d+)\.html")


@dataclass(frozen=True)
class OfferId:
    value: str

    @classmethod
    def parse(cls, raw: object) -> OfferId | None:
        if raw is None:
            return None

        text = str(raw).strip()
        if not text:
            return None

        matched = _OFFER_IN_URL.search(text)
        if matched:
            return cls(matched.group(1))

        return cls(text) if _DIGITS.match(text) else None

    @property
    def detail_url(self) -> str:
        return f"https://detail.1688.com/offer/{self.value}.html"

    def __str__(self) -> str:
        return self.value
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_offer_id.py -v`
Expected: PASS（8件）

- [ ] **Step 5: SupplierCandidate の失敗するテストを書く**

`src/tests/test_supplier_candidate.py`:

```python
from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId


class TestSupplierCandidate:
    def test_商品URLを組み立てる(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("620082943880"),
            title="源头工厂钕铁硼强磁现货直发圆形磁铁",
            company="雄尊磁铁厂",
            province="浙江",
            local_price=0.03,
        )
        assert candidate.url == "https://detail.1688.com/offer/620082943880.html"

    def test_価格が不明でも生成できる(self) -> None:
        candidate = SupplierCandidate(
            offer_id=OfferId("853573456382"),
            title="现货钕铁硼强力圆形10*2磁铁",
            company="丽嘉磁业工厂",
            province="广东",
            local_price=None,
        )
        assert candidate.local_price is None
        assert candidate.url == "https://detail.1688.com/offer/853573456382.html"
```

- [ ] **Step 6: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_supplier_candidate.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 7: SupplierCandidate を実装する**

`src/domain/entities/supplier_candidate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.offer_id import OfferId


@dataclass(frozen=True)
class SupplierCandidate:
    offer_id: OfferId
    title: str
    company: str
    province: str
    local_price: float | None

    @property
    def url(self) -> str:
        return self.offer_id.detail_url
```

- [ ] **Step 8: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_offer_id.py src/tests/test_supplier_candidate.py -v`
Expected: PASS（10件）

- [ ] **Step 9: コミットする**

```bash
git add src/domain/value_objects/offer_id.py src/domain/entities/supplier_candidate.py \
        src/tests/test_offer_id.py src/tests/test_supplier_candidate.py
git commit -m "feat: 1688の仕入先候補を表すOfferIdとSupplierCandidateを追加"
```

---

### Task 2: 1行目のコードで列を引く

**Files:**
- Create: `src/infrastructure/column_codes.py`
- Test: `src/tests/test_column_codes.py`

**Interfaces:**
- Consumes: `src.infrastructure.column_mapper.normalize_header`
- Produces: `ColumnCodes(values: list[list])`、`ColumnCodes.index_of(code: str) -> int | None`

**背景:** `SheetTable` のヘッダーは3行目（空なら2行目）を使うため、AR と AW がどちらも `名称` になり区別できない。1行目には `LINK_BUY_OTHER1` / `LINK_BUY_OTHER2` という一意のコードがあるので、書き込み先はこちらで引く。`sheet_repository.py` は並行セッションが触っているため変更しない。

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_column_codes.py`:

```python
from src.infrastructure.column_codes import ColumnCodes

VALUES = [
    ["んh", "CHECK2", "ASIN_SELL", "", "", "IMAGE", "LINK_LOWEST", "PRICE_LOWEST",
     "LOCALPRICE_LOWEST", "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "LINK_BUY_OTHER2"],
    ["", "", "ASIN", "", "", "画像URL", "購入先", "購入\n価格", "現地\n価格", "他仕入先1", "", "他仕入先2"],
    ["0", "1", "", "JAN/EAN", "UPC", "", "", "", "", "名称", "価格", "名称"],
    ["", "", "B0CCX6ZXRV"],
]


class TestColumnCodes:
    def test_コードから列番号を引く(self) -> None:
        codes = ColumnCodes(VALUES)
        assert codes.index_of("LINK_LOWEST") == 6
        assert codes.index_of("ASIN_SELL") == 2
        assert codes.index_of("IMAGE") == 5

    def test_名称が重複していても他仕入先を区別できる(self) -> None:
        codes = ColumnCodes(VALUES)
        assert codes.index_of("LINK_BUY_OTHER1") == 9
        assert codes.index_of("LINK_BUY_OTHER2") == 11

    def test_存在しないコードはNoneを返す(self) -> None:
        assert ColumnCodes(VALUES).index_of("CURRENCY_BUY_OTHER9") is None

    def test_前後の空白と改行を無視して一致させる(self) -> None:
        codes = ColumnCodes([[" LINK_LOWEST\n"], [""], [""]])
        assert codes.index_of("LINK_LOWEST") == 0

    def test_空のシートでもNoneを返す(self) -> None:
        assert ColumnCodes([]).index_of("LINK_LOWEST") is None
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_column_codes.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.infrastructure.column_codes'`）

- [ ] **Step 3: 実装する**

`src/infrastructure/column_codes.py`:

```python
from __future__ import annotations

from src.infrastructure.column_mapper import normalize_header

CODE_ROW = 1


class ColumnCodes:
    def __init__(self, values: list[list], code_row: int = CODE_ROW) -> None:
        row = values[code_row - 1] if len(values) >= code_row else []
        self._index = {
            normalize_header(cell): position
            for position, cell in enumerate(row)
            if normalize_header(cell)
        }

    def index_of(self, code: str) -> int | None:
        return self._index.get(code)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_column_codes.py -v`
Expected: PASS（5件）

- [ ] **Step 5: コミットする**

```bash
git add src/infrastructure/column_codes.py src/tests/test_column_codes.py
git commit -m "feat: 1行目のコードで列を引くColumnCodesを追加"
```

---

### Task 3: F列の数式から画像URLを取り出す

**Files:**
- Create: `src/infrastructure/image_formula.py`
- Test: `src/tests/test_image_formula.py`

**Interfaces:**
- Consumes: なし
- Produces: `extract_image_url(cell: object) -> str | None`

**背景:** F列は `=HYPERLINK("<商品URL>", IMAGE("<画像URL>"))` の数式。`GoogleSheetRepository.read_table` は `FORMULA` で読むため、数式文字列がそのまま入る。

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_image_formula.py`:

```python
from src.infrastructure.image_formula import extract_image_url


class TestExtractImageUrl:
    def test_HYPERLINKとIMAGEの数式から画像URLを取り出す(self) -> None:
        cell = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
        assert extract_image_url(cell) == "https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"

    def test_IMAGEのみの数式からも取り出す(self) -> None:
        cell = '=IMAGE("https://m.media-amazon.com/images/I/71RCFDW42qL.jpg")'
        assert extract_image_url(cell) == "https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"

    def test_素のURLはそのまま返す(self) -> None:
        cell = "https://m.media-amazon.com/images/I/71RCFDW42qL.jpg"
        assert extract_image_url(cell) == cell

    def test_空はNoneを返す(self) -> None:
        assert extract_image_url("") is None
        assert extract_image_url(None) is None

    def test_画像を含まない数式はNoneを返す(self) -> None:
        assert extract_image_url('=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", "商品")') is None

    def test_商品URLの方を誤って返さない(self) -> None:
        cell = '=HYPERLINK("https://www.amazon.co.jp/dp/B0CCX6ZXRV", IMAGE("https://m.media-amazon.com/images/I/61HWhaAyRKL.jpg"))'
        assert "amazon.co.jp" not in extract_image_url(cell)
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_image_formula.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装する**

`src/infrastructure/image_formula.py`:

```python
from __future__ import annotations

import re

_IMAGE_ARGUMENT = re.compile(r'IMAGE\(\s*"([^"]+)"', re.IGNORECASE)


def extract_image_url(cell: object) -> str | None:
    if cell is None:
        return None

    text = str(cell).strip()
    if not text:
        return None

    matched = _IMAGE_ARGUMENT.search(text)
    if matched:
        return matched.group(1)

    return text if text.lower().startswith("http") else None
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_image_formula.py -v`
Expected: PASS（6件）

- [ ] **Step 5: コミットする**

```bash
git add src/infrastructure/image_formula.py src/tests/test_image_formula.py
git commit -m "feat: F列の数式から画像URLを取り出すextract_image_urlを追加"
```

---

### Task 4: 対象行を選ぶ

**Files:**
- Create: `src/usecases/select_supplier_targets.py`
- Test: `src/tests/test_select_supplier_targets.py`

**Interfaces:**
- Consumes: `ColumnCodes.index_of`、`extract_image_url`、`SheetTable.data_rows`、`SheetTable.row_number`
- Produces: `SupplierTarget(row_number: int, asin: str, image_url: str)`、`select_targets(table, codes, limit: int = 10) -> list[SupplierTarget]`

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_select_supplier_targets.py`:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_select_supplier_targets.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装する**

`src/usecases/select_supplier_targets.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.image_formula import extract_image_url
from src.infrastructure.sheet_repository import SheetTable

DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class SupplierTarget:
    row_number: int
    asin: str
    image_url: str


def _cell(row: list, index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return str(row[index]).strip()


def select_targets(
    table: SheetTable, codes: ColumnCodes, limit: int = DEFAULT_LIMIT
) -> list[SupplierTarget]:
    asin_index = codes.index_of("ASIN_SELL")
    image_index = codes.index_of("IMAGE")
    link_index = codes.index_of("LINK_LOWEST")

    targets: list[SupplierTarget] = []

    for data_index, row in enumerate(table.data_rows):
        if len(targets) >= limit:
            break
        if _cell(row, link_index):
            continue

        image_url = extract_image_url(_cell(row, image_index))
        if not image_url:
            continue

        targets.append(
            SupplierTarget(
                row_number=table.row_number(data_index),
                asin=_cell(row, asin_index),
                image_url=image_url,
            )
        )

    return targets
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_select_supplier_targets.py -v`
Expected: PASS（5件）

- [ ] **Step 5: コミットする**

```bash
git add src/usecases/select_supplier_targets.py src/tests/test_select_supplier_targets.py
git commit -m "feat: 購入先が空で画像がある行を選ぶselect_targetsを追加"
```

---

### Task 5: 書き込む値を組み立てる

**Files:**
- Create: `src/usecases/build_supplier_updates.py`
- Test: `src/tests/test_build_supplier_updates.py`

**Interfaces:**
- Consumes: `SupplierCandidate`、`ColumnCodes.index_of`、`src.infrastructure.sheet_repository.column_letter`
- Produces: `build_updates(row_number: int, candidates: list[SupplierCandidate], codes: ColumnCodes) -> dict[int, object]`（キーは0始まりの列番号）

**背景:** 1件目は購入先の枠に入り、通貨列が存在しない。2件目以降は通貨に `CHY` を書く。価格（円）は現地価格を参照する数式にする。直送送料には書かない。

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_build_supplier_updates.py`:

```python
import pytest

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId
from src.infrastructure.column_codes import ColumnCodes
from src.usecases.build_supplier_updates import build_updates

CODE_ROW = [
    "LINK_LOWEST",            # 0
    "PRICE_LOWEST",           # 1
    "LOCALPRICE_LOWEST",      # 2
    "SHIPPING_INTL",          # 3
    "LINK_BUY_OTHER1",        # 4
    "PRICE_BUY_OTHER1",       # 5
    "CURRENCY_BUY_OTHER1",    # 6
    "LOCALPRICE_BUY_OTHER1",  # 7
    "SHIPPING_INTL_OTHER1",   # 8
    "LINK_BUY_OTHER2",        # 9
    "PRICE_BUY_OTHER2",       # 10
    "CURRENCY_BUY_OTHER2",    # 11
    "LOCALPRICE_BUY_OTHER2",  # 12
    "SHIPPING_INTL_OTHER2",   # 13
]


@pytest.fixture
def codes() -> ColumnCodes:
    return ColumnCodes([CODE_ROW, [], []])


def candidate(offer: str, price: float | None) -> SupplierCandidate:
    return SupplierCandidate(
        offer_id=OfferId(offer),
        title="强力磁铁",
        company="雄尊磁铁厂",
        province="浙江",
        local_price=price,
    )


class TestBuildUpdates:
    def test_1件目は購入先に入り通貨は書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", 0.03)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert updates[2] == 0.03
        assert updates[1] == "=C5*24"

    def test_2件目は通貨CHYを書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5, [candidate("1", 0.03), candidate("853573456382", 0.05)], codes
        )
        assert updates[4] == "https://detail.1688.com/offer/853573456382.html"
        assert updates[6] == "CHY"
        assert updates[7] == 0.05
        assert updates[5] == "=H5*24"

    def test_3件目も通貨CHYを書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            9, [candidate("1", 0.01), candidate("2", 0.02), candidate("956382552398", 0.09)], codes
        )
        assert updates[9] == "https://detail.1688.com/offer/956382552398.html"
        assert updates[11] == "CHY"
        assert updates[12] == 0.09
        assert updates[10] == "=M9*24"

    def test_直送送料には書かない(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5, [candidate("1", 0.01), candidate("2", 0.02), candidate("3", 0.03)], codes
        )
        assert 8 not in updates
        assert 13 not in updates

    def test_候補が2件なら3件目の列は触らない(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("1", 0.01), candidate("2", 0.02)], codes)
        assert 9 not in updates
        assert 11 not in updates

    def test_候補が0件なら何も書かない(self, codes: ColumnCodes) -> None:
        assert build_updates(5, [], codes) == {}

    def test_価格が不明なら価格と現地価格を書かずURLだけ書く(self, codes: ColumnCodes) -> None:
        updates = build_updates(5, [candidate("620082943880", None)], codes)
        assert updates[0] == "https://detail.1688.com/offer/620082943880.html"
        assert 1 not in updates
        assert 2 not in updates

    def test_4件目以降は無視する(self, codes: ColumnCodes) -> None:
        updates = build_updates(
            5,
            [candidate("1", 0.01), candidate("2", 0.02), candidate("3", 0.03), candidate("4", 0.04)],
            codes,
        )
        assert len([v for v in updates.values() if str(v).startswith("https://")]) == 3
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_build_supplier_updates.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装する**

`src/usecases/build_supplier_updates.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import column_letter

CURRENCY = "CHY"
CNY_TO_JPY_RATE = 24


@dataclass(frozen=True)
class CandidateSlot:
    link: str
    price: str
    local_price: str
    currency: str | None


SLOTS = (
    CandidateSlot("LINK_LOWEST", "PRICE_LOWEST", "LOCALPRICE_LOWEST", None),
    CandidateSlot(
        "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "LOCALPRICE_BUY_OTHER1", "CURRENCY_BUY_OTHER1"
    ),
    CandidateSlot(
        "LINK_BUY_OTHER2", "PRICE_BUY_OTHER2", "LOCALPRICE_BUY_OTHER2", "CURRENCY_BUY_OTHER2"
    ),
)


def _put(updates: dict[int, object], index: int | None, value: object) -> None:
    if index is not None:
        updates[index] = value


def build_updates(
    row_number: int, candidates: list[SupplierCandidate], codes: ColumnCodes
) -> dict[int, object]:
    updates: dict[int, object] = {}

    for slot, candidate in zip(SLOTS, candidates):
        _put(updates, codes.index_of(slot.link), candidate.url)

        if slot.currency:
            _put(updates, codes.index_of(slot.currency), CURRENCY)

        if candidate.local_price is None:
            continue

        local_index = codes.index_of(slot.local_price)
        _put(updates, local_index, candidate.local_price)

        if local_index is not None:
            formula = f"={column_letter(local_index)}{row_number}*{CNY_TO_JPY_RATE}"
            _put(updates, codes.index_of(slot.price), formula)

    return updates
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_build_supplier_updates.py -v`
Expected: PASS（8件）

- [ ] **Step 5: コミットする**

```bash
git add src/usecases/build_supplier_updates.py src/tests/test_build_supplier_updates.py
git commit -m "feat: 仕入先候補3件をシートの各枠へ割り当てるbuild_updatesを追加"
```

---

### Task 6: 書き込んだセルをグレーにする

**Files:**
- Create: `src/infrastructure/cell_highlighter.py`
- Test: `src/tests/test_cell_highlighter.py`

**Interfaces:**
- Consumes: `src.infrastructure.sheet_repository.column_letter`
- Produces: `build_highlight_requests(cells: list[tuple[int, int]]) -> list[dict]`、`apply_highlight(worksheet, cells: list[tuple[int, int]]) -> int`（`cells` は `(行番号, 0始まりの列番号)`）

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_cell_highlighter.py`:

```python
from src.infrastructure.cell_highlighter import (
    FILLED_BACKGROUND,
    apply_highlight,
    build_highlight_requests,
)


class FakeWorksheet:
    def __init__(self) -> None:
        self.received: list[dict] = []

    def batch_format(self, formats: list[dict]) -> None:
        self.received = formats


class TestBuildHighlightRequests:
    def test_セルをA1形式のレンジに変換する(self) -> None:
        requests = build_highlight_requests([(5, 0), (5, 6)])
        assert [r["range"] for r in requests] == ["A5", "G5"]

    def test_背景色を指定する(self) -> None:
        requests = build_highlight_requests([(5, 0)])
        assert requests[0]["format"] == {"backgroundColor": FILLED_BACKGROUND}

    def test_行と列の順に並べる(self) -> None:
        requests = build_highlight_requests([(9, 2), (5, 6), (5, 0)])
        assert [r["range"] for r in requests] == ["A5", "G5", "C9"]

    def test_空なら空リストを返す(self) -> None:
        assert build_highlight_requests([]) == []


class TestApplyHighlight:
    def test_ワークシートへまとめて渡す(self) -> None:
        worksheet = FakeWorksheet()
        count = apply_highlight(worksheet, [(5, 0), (5, 6)])
        assert count == 2
        assert [r["range"] for r in worksheet.received] == ["A5", "G5"]

    def test_空なら呼び出さない(self) -> None:
        worksheet = FakeWorksheet()
        assert apply_highlight(worksheet, []) == 0
        assert worksheet.received == []
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_cell_highlighter.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装する**

`src/infrastructure/cell_highlighter.py`:

```python
from __future__ import annotations

from src.infrastructure.sheet_repository import column_letter

# 自動で埋めたセルを手入力と区別するための薄いグレー (#EDEDED)
FILLED_BACKGROUND = {"red": 0.929, "green": 0.929, "blue": 0.929}


def build_highlight_requests(cells: list[tuple[int, int]]) -> list[dict]:
    return [
        {
            "range": f"{column_letter(column)}{row_number}",
            "format": {"backgroundColor": FILLED_BACKGROUND},
        }
        for row_number, column in sorted(cells)
    ]


def apply_highlight(worksheet, cells: list[tuple[int, int]]) -> int:
    requests = build_highlight_requests(cells)
    if not requests:
        return 0

    worksheet.batch_format(requests)
    return len(requests)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_cell_highlighter.py -v`
Expected: PASS（6件）

- [ ] **Step 5: コミットする**

```bash
git add src/infrastructure/cell_highlighter.py src/tests/test_cell_highlighter.py
git commit -m "feat: 自動で埋めたセルをグレーにするcell_highlighterを追加"
```

---

### Task 7: ブラウザの出力を候補に変換する

**Files:**
- Create: `src/infrastructure/candidate_parser.py`
- Test: `src/tests/test_candidate_parser.py`

**Interfaces:**
- Consumes: `OfferId.parse`、`SupplierCandidate`
- Produces: `parse_candidates(raw_items: list[dict], limit: int = 3) -> list[SupplierCandidate]`

**背景:** ブラウザ内の JS（Task 8）が返す JSON を受け取る。`offerId` が無い・重複するものは落とし、上位から `limit` 件を採る。価格は取得できないことがある。

- [ ] **Step 1: 失敗するテストを書く**

`src/tests/test_candidate_parser.py`:

```python
from src.infrastructure.candidate_parser import parse_candidates


def raw(offer_id: object, price: object = 0.03) -> dict:
    return {
        "offerId": offer_id,
        "title": "强力磁铁",
        "company": "雄尊磁铁厂",
        "province": "浙江",
        "price": price,
    }


class TestParseCandidates:
    def test_上位3件を返す(self) -> None:
        items = [raw("1"), raw("2"), raw("3"), raw("4")]
        candidates = parse_candidates(items)
        assert [c.offer_id.value for c in candidates] == ["1", "2", "3"]

    def test_重複するofferIdを除外する(self) -> None:
        items = [raw("620082943880"), raw("620082943880"), raw("853573456382")]
        candidates = parse_candidates(items)
        assert [c.offer_id.value for c in candidates] == ["620082943880", "853573456382"]

    def test_offerIdが無い要素を除外する(self) -> None:
        candidates = parse_candidates([raw(None), raw("abc"), raw("620082943880")])
        assert [c.offer_id.value for c in candidates] == ["620082943880"]

    def test_価格が取れない場合はNoneにする(self) -> None:
        candidates = parse_candidates([raw("1", None), raw("2", "false"), raw("3", "")])
        assert [c.local_price for c in candidates] == [None, None, None]

    def test_文字列の価格を数値にする(self) -> None:
        candidates = parse_candidates([raw("1", "0.03")])
        assert candidates[0].local_price == 0.03

    def test_欠けている項目は空文字にする(self) -> None:
        candidates = parse_candidates([{"offerId": "620082943880"}])
        assert candidates[0].title == ""
        assert candidates[0].company == ""
        assert candidates[0].province == ""

    def test_空の入力なら空リストを返す(self) -> None:
        assert parse_candidates([]) == []
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_candidate_parser.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装する**

`src/infrastructure/candidate_parser.py`:

```python
from __future__ import annotations

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId

DEFAULT_LIMIT = 3


def _to_price(raw: object) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def _to_text(raw: object) -> str:
    return "" if raw is None else str(raw).strip()


def parse_candidates(
    raw_items: list[dict], limit: int = DEFAULT_LIMIT
) -> list[SupplierCandidate]:
    candidates: list[SupplierCandidate] = []
    seen: set[str] = set()

    for item in raw_items:
        if len(candidates) >= limit:
            break

        offer_id = OfferId.parse(item.get("offerId"))
        if offer_id is None or offer_id.value in seen:
            continue

        seen.add(offer_id.value)
        candidates.append(
            SupplierCandidate(
                offer_id=offer_id,
                title=_to_text(item.get("title")),
                company=_to_text(item.get("company")),
                province=_to_text(item.get("province")),
                local_price=_to_price(item.get("price")),
            )
        )

    return candidates
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests/test_candidate_parser.py -v`
Expected: PASS（7件）

- [ ] **Step 5: コミットする**

```bash
git add src/infrastructure/candidate_parser.py src/tests/test_candidate_parser.py
git commit -m "feat: ブラウザの出力を仕入先候補に変換するparse_candidatesを追加"
```

---

### Task 8: ページ内で候補を取り出す JS

**Files:**
- Create: `scripts/extract_candidates.js`

**Interfaces:**
- Consumes: なし（ブラウザで実行）
- Produces: `[{offerId, title, company, province, price}]` の JSON 文字列。Task 7 の `parse_candidates` が受け取る形

**背景:** 商品カードはアンカーではないため、`img[src*="cbu01.alicdn.com"]` から React の内部状態（`__reactFiber$`）を12階層まで遡って `offerId` を持つオブジェクトを探す。価格のプロパティ名は不明なので、カードの表示テキストから `¥` の数値を拾う。

**注意:** クエリ文字列を含む値（`impressionEurl` など）を返すとツール側で遮断されるため、必要な項目だけを選んで返す。

- [ ] **Step 1: スクリプトを作成する**

`scripts/extract_candidates.js`:

```javascript
// 1688 の画像検索結果ページで実行し、上位の仕入先候補を JSON で返す。
// 商品カードは React 要素でリンクを持たないため、内部状態から offerId を取る。
(() => {
  const LIMIT = 10;

  function findOffer(element) {
    const key = Object.keys(element).find(k => k.startsWith('__reactFiber$'));
    if (!key) return null;

    let node = element[key];
    for (let depth = 0; depth < 12 && node; depth++) {
      const props = node.memoizedProps || node.pendingProps;
      if (props && typeof props === 'object') {
        for (const value of Object.values(props)) {
          if (value && typeof value === 'object' && value.offerId) return value;
        }
      }
      node = node.return;
    }
    return null;
  }

  function findPrice(element) {
    let node = element;
    for (let depth = 0; depth < 8 && node; depth++) {
      const matched = (node.innerText || '').match(/¥\s*([\d.]+)/);
      if (matched) return parseFloat(matched[1]);
      node = node.parentElement;
    }
    return null;
  }

  const seen = new Set();
  const items = [];

  for (const image of document.querySelectorAll('img[src*="cbu01.alicdn.com"]')) {
    if (items.length >= LIMIT) break;

    const offer = findOffer(image);
    if (!offer || seen.has(String(offer.offerId))) continue;
    seen.add(String(offer.offerId));

    items.push({
      offerId: String(offer.offerId),
      title: String(offer.title || offer.subject || '').replace(/<[^>]*>/g, '').slice(0, 60),
      company: String(offer.companyName || offer.loginId || '').slice(0, 40),
      province: String(offer.province || ''),
      price: findPrice(image)
    });
  }

  return JSON.stringify(items);
})()
```

- [ ] **Step 2: コミットする**

```bash
git add scripts/extract_candidates.js
git commit -m "feat: 1688の検索結果から候補を取り出すJSを追加"
```

---

### Task 9: /find-supplier コマンド

**Files:**
- Create: `.claude/commands/find-supplier.md`
- Create: `find_supplier.py`

**Interfaces:**
- Consumes: `select_targets`、`parse_candidates`、`build_updates`、`apply_highlight`、`GoogleSheetRepository`
- Produces: CLI `find_supplier.py targets --sheet <名前> [--limit N]` と `find_supplier.py write --sheet <名前> --row N --candidates <JSONファイル>`

**背景:** ブラウザ操作は Claude が手順として行い、シートの読み書きだけを Python に任せる2段構成にする。`targets` で対象行と画像URLを出し、行ごとにブラウザで検索し、`write` で書き戻す。

- [ ] **Step 1: CLI を作成する**

`find_supplier.py`:

```python
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.candidate_parser import parse_candidates
from src.infrastructure.cell_highlighter import apply_highlight
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository, SheetTable
from src.usecases.build_supplier_updates import build_updates
from src.usecases.select_supplier_targets import select_targets

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def build_repository() -> GoogleSheetRepository:
    load_dotenv(PROJECT_ROOT / ".env")
    return GoogleSheetRepository(
        str(PROJECT_ROOT / os.environ["SERVICE_ACCOUNT_FILE"]),
        os.environ["RESEARCH_SPREADSHEET_ID"],
    )


def read_values(repository: GoogleSheetRepository, sheet_name: str) -> tuple[list[list], object]:
    worksheet = repository.spreadsheet.worksheet(sheet_name)
    return worksheet.get_values(value_render_option="FORMULA"), worksheet


def run_targets(args: argparse.Namespace) -> int:
    repository = build_repository()
    values, _ = read_values(repository, args.sheet)

    targets = select_targets(SheetTable(values), ColumnCodes(values), limit=args.limit)

    print(json.dumps([asdict(target) for target in targets], ensure_ascii=False, indent=1))
    logger.info("対象行を抽出しました", extra={"context": {"count": len(targets)}})
    return 0


def run_write(args: argparse.Namespace) -> int:
    repository = build_repository()
    values, worksheet = read_values(repository, args.sheet)
    codes = ColumnCodes(values)

    raw_items = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    candidates = parse_candidates(raw_items)
    updates = build_updates(args.row, candidates, codes)

    if not updates:
        logger.warning("候補が無いため書き込みません", extra={"context": {"row": args.row}})
        return 0

    repository.apply_updates(args.sheet, {args.row: updates})
    apply_highlight(worksheet, [(args.row, column) for column in updates])

    logger.info(
        "仕入先候補を書き込みました",
        extra={"context": {"row": args.row, "cells": len(updates)}},
    )
    return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    targets = subparsers.add_parser("targets")
    targets.add_argument("--sheet", required=True)
    targets.add_argument("--limit", type=int, default=10)
    targets.set_defaults(func=run_targets)

    write = subparsers.add_parser("write")
    write.add_argument("--sheet", required=True)
    write.add_argument("--row", type=int, required=True)
    write.add_argument("--candidates", required=True)
    write.set_defaults(func=run_write)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 全テストが通ることを確認する**

Run: `.venv/bin/python -m pytest src/tests -v`
Expected: PASS（既存のテストも含めて全件）

- [ ] **Step 3: 対象行の抽出だけを実行して確認する**

Run: `.venv/bin/python find_supplier.py targets --sheet "リサーチ700円以下" --limit 3`
Expected: `row_number` `asin` `image_url` を持つ JSON が最大3件。**シートは変更されない**

- [ ] **Step 4: コマンド手順を作成する**

`.claude/commands/find-supplier.md`:

````markdown
# /find-supplier

リサーチシートの商品画像から 1688 の同款を画像検索し、上位3件を仕入先候補として登録する。

## 前提

1688 はヘッドレスでは開けない（`验证码拦截` で遮断される）。
**必ず claude-in-chrome（ユーザーのログイン済み Chrome）を使う。**

## Step 1: 対象行を出す

```bash
.venv/bin/python find_supplier.py targets --sheet "<シート名>" --limit 10
```

購入先が空で画像がある行だけが返る。0件なら終了する。

## Step 2: 行ごとに画像検索する

各行について次を繰り返す。

1. 画像を作業ディレクトリへ落とす

   ```bash
   curl -s -o <scratchpad>/<ASIN>.jpg "<image_url>"
   ```

2. 検索ページを開く（`mcp__claude-in-chrome__navigate`）

   ```
   https://s.1688.com/youyuan/index.htm?tab=imageSearch
   ```

3. ファイル入力を探す（`mcp__claude-in-chrome__find`、`file input for uploading a local image`）
4. `mcp__claude-in-chrome__file_upload` で画像を投入する
5. 「搜索图片」を `find` で探して `computer` の `left_click` で押す
6. 5秒待つ
7. `scripts/extract_candidates.js` の中身を `mcp__claude-in-chrome__javascript_tool` で実行する
8. 返ってきた JSON を作業ディレクトリへ保存する
9. 書き戻す

   ```bash
   .venv/bin/python find_supplier.py write --sheet "<シート名>" --row <行番号> --candidates <JSONファイル>
   ```

## 注意

- **`imageAddress` パラメータで画像URLを渡してはいけない。** 画像は表示されるが検索結果が0件になる
- **キャプチャが出たら停止する。** ユーザーに手動での通過を依頼し、以降の行は処理しない
- 検索結果が0件だった行は何も書かず、ASIN をログに残して次へ進む
- 開いたタブは `mcp__claude-in-chrome__tabs_close_mcp` で閉じる
````

- [ ] **Step 5: コミットする**

```bash
git add find_supplier.py .claude/commands/find-supplier.md
git commit -m "feat: /find-supplier コマンドとCLIを追加"
```

---

### Task 10: 1行で通しで動かす

**Files:**
- Modify: `docs/superpowers/specs/2026-08-23-find-supplier-design.md`（価格の取得方法が確定したら追記）

**Interfaces:**
- Consumes: Task 9 までのすべて
- Produces: なし（受け入れ確認）

- [ ] **Step 1: 対象行を1件だけ出す**

Run: `.venv/bin/python find_supplier.py targets --sheet "リサーチ700円以下" --limit 1`
Expected: 1件の JSON

- [ ] **Step 2: `.claude/commands/find-supplier.md` の Step 2 を手で1周する**

Expected: 候補 JSON に `offerId` が3件入り、`price` が `null` でない

- [ ] **Step 3: シートを目視で確認する**

Expected:
- 購入先・他仕入先1・他仕入先2に `https://detail.1688.com/offer/...` が入っている
- 通貨列が `CHY`
- 価格列が `=<現地価格列><行番号>*24` の数式で、円の金額が表示されている
- 直送送料は空のまま
- **書き込んだセルだけ背景がグレー**

- [ ] **Step 4: 価格が取れなかった場合は JS を直す**

`scripts/extract_candidates.js` の `findPrice` が `null` を返す場合、カードの構造を
`mcp__claude-in-chrome__read_page` で確認し、`¥` を含む要素までの深さを 8 から増やす。
直したら Task 8 のコミットに追加でコミットする。

- [ ] **Step 5: 動いた内容を仕様書へ反映してコミットする**

```bash
git add docs/superpowers/specs/2026-08-23-find-supplier-design.md
git commit -m "docs: 価格の取得方法を確定して仕様書へ反映"
```
