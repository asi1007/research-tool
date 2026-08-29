# 売れ筋新商品の自動発見（/market-research）実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keepa Product Finder で「発売半年以内・月販1000個以上・1000円以下」の商品を洗い出し、既知でない ASIN だけをリサーチシートの「自動調査」タブへ積んで、続けて既存の `fetch_products.py` で中身を埋める。

**Architecture:** 条件は値オブジェクト `DiscoveryCriteria` に集約し、Keepa の `selection` へ変換する。`KeepaClient` に `/query` を叩く `find_asins()` を足す。突合と追記行の組み立ては純粋関数として usecase に置き、Sheets と Keepa への実アクセスは infrastructure に閉じる。CLI は発見 → 追記 → `fetch_products.py` 呼び出しの順に並べるだけ。

**Tech Stack:** Python 3.10+ / requests / gspread / pytest / launchd

**Spec:** `docs/superpowers/specs/2026-08-29-market-research-design.md`

## Global Constraints

- 型ヒントを必ず付ける。docstring は書かない（変数名と型で説明する）
- 列は**1行目の列コード**を `ColumnCodes` で引く。列インデックスを固定しない
- Sheets の書き込みは `GoogleSheetRepository.apply_updates()` にまとめる（60req/min 制限）
- ログは既存の `configure_logging()` による JSON 構造化ログ。`extra={"context": {...}}` で文脈を付ける
- テストは `src/tests/` に置き、メソッド名は日本語（既存の `test_keepa_client.py` に倣う）
- 対象スプレッドシート: `RESEARCH_SPREADSHEET_ID`（`.env`）、書き込み先タブは `自動調査`
- Keepa: `domain=5`、`POST /query`、**`perPage` は 50 以上**、1回 11トークン
- コミットのたびに `pyproject.toml` の `version` を更新する（現在 `0.5.4`）
- コミットは `git add <パス>` でファイルを個別指定する（同じ作業ディレクトリを他セッションが共有している）

---

### Task 1: 抽出条件の値オブジェクト

**Files:**
- Create: `src/domain/value_objects/discovery_criteria.py`
- Test: `src/tests/test_discovery_criteria.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `EXCLUDED_ROOT_CATEGORIES: tuple[int, ...]`
  - `DiscoveryCriteria(max_price_yen: int = 1000, min_monthly_sold: int = 1000, max_age_days: int = 180, excluded_categories: tuple[int, ...] = EXCLUDED_ROOT_CATEGORIES, per_page: int = 50)`
  - `DiscoveryCriteria.selection(self, now: datetime, page: int = 0) -> dict`
  - `to_keepa_minutes(moment: datetime) -> int`

- [ ] **Step 1: Write the failing test**

`src/tests/test_discovery_criteria.py`:

```python
from datetime import datetime, timezone

import pytest

from src.domain.value_objects.discovery_criteria import (
    EXCLUDED_ROOT_CATEGORIES,
    DiscoveryCriteria,
    to_keepa_minutes,
)

NOW = datetime(2026, 8, 29, 0, 0, tzinfo=timezone.utc)


class TestKeepaMinutes:
    def test_エポックからの経過分に変換する(self) -> None:
        assert to_keepa_minutes(datetime(2011, 1, 1, 0, 0, tzinfo=timezone.utc)) == 0
        assert to_keepa_minutes(datetime(2011, 1, 1, 1, 0, tzinfo=timezone.utc)) == 60


class TestSelection:
    def test_必須の3条件を組み立てる(self) -> None:
        selection = DiscoveryCriteria().selection(NOW)

        assert selection["current_NEW_gte"] == 1
        assert selection["current_NEW_lte"] == 1000
        assert selection["monthlySold_gte"] == 1000
        assert selection["listedSince_gte"] == to_keepa_minutes(
            datetime(2026, 3, 2, 0, 0, tzinfo=timezone.utc)
        )

    def test_Amazon本体とバリエーション親を除外する(self) -> None:
        selection = DiscoveryCriteria().selection(NOW)

        assert selection["availabilityAmazon"] == [-1]
        assert selection["productType"] == [0]

    def test_除外カテゴリは18件で本と食品を含む(self) -> None:
        assert len(EXCLUDED_ROOT_CATEGORIES) == 18
        assert 465392 in EXCLUDED_ROOT_CATEGORIES
        assert 57239051 in EXCLUDED_ROOT_CATEGORIES

    def test_ビューティーとパソコン周辺は除外しない(self) -> None:
        assert 52374051 not in EXCLUDED_ROOT_CATEGORIES
        assert 2127209051 not in EXCLUDED_ROOT_CATEGORIES

    def test_月販の降順で取り出す(self) -> None:
        assert DiscoveryCriteria().selection(NOW)["sort"] == [["monthlySold", "desc"]]

    def test_ページ番号を差し替えられる(self) -> None:
        assert DiscoveryCriteria().selection(NOW, page=2)["page"] == 2
        assert DiscoveryCriteria().selection(NOW)["perPage"] == 50

    def test_perPageが50未満なら作れない(self) -> None:
        with pytest.raises(ValueError, match="perPage"):
            DiscoveryCriteria(per_page=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/tests/test_discovery_criteria.py -v`
Expected: FAIL（`ModuleNotFoundError: src.domain.value_objects.discovery_criteria`）

- [ ] **Step 3: Write minimal implementation**

`src/domain/value_objects/discovery_criteria.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
MIN_PER_PAGE = 50

# 中国輸入で扱えないルートカテゴリ。IDは Keepa /category（domain=5）で取得したもの
EXCLUDED_ROOT_CATEGORIES: tuple[int, ...] = (
    465392,      # 本
    52033011,    # 洋書
    561956,      # ミュージック
    561958,      # DVD
    2128134051,  # デジタルミュージック
    2250738051,  # Kindleストア
    2351649051,  # Prime Video
    2381130051,  # アプリ＆ゲーム
    4788676051,  # Alexaスキル
    637392,      # PCソフト
    637394,      # ゲーム
    2320455051,  # ファイナンス
    4976279051,  # Amazonデバイス・アクセサリ
    160384011,   # ドラッグストア
    57239051,    # 食品・飲料・お酒
    344845011,   # ベビー＆マタニティ
    2277724051,  # 大型家電
    3210981,     # 家電＆カメラ
)

STANDARD_PRODUCT_TYPE = 0
NO_AMAZON_OFFER = -1


def to_keepa_minutes(moment: datetime) -> int:
    return int((moment - KEEPA_EPOCH).total_seconds() // 60)


@dataclass(frozen=True)
class DiscoveryCriteria:
    max_price_yen: int = 1000
    min_monthly_sold: int = 1000
    max_age_days: int = 180
    excluded_categories: tuple[int, ...] = field(default=EXCLUDED_ROOT_CATEGORIES)
    per_page: int = MIN_PER_PAGE

    def __post_init__(self) -> None:
        if self.per_page < MIN_PER_PAGE:
            raise ValueError(f"perPage は {MIN_PER_PAGE} 以上にする（Keepa が 400 を返す）")

    def selection(self, now: datetime, page: int = 0) -> dict:
        listed_since = now - timedelta(days=self.max_age_days)
        return {
            "current_NEW_gte": 1,
            "current_NEW_lte": self.max_price_yen,
            "monthlySold_gte": self.min_monthly_sold,
            "listedSince_gte": to_keepa_minutes(listed_since),
            "productType": [STANDARD_PRODUCT_TYPE],
            "availabilityAmazon": [NO_AMAZON_OFFER],
            "categories_exclude": list(self.excluded_categories),
            "sort": [["monthlySold", "desc"]],
            "perPage": self.per_page,
            "page": page,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/tests/test_discovery_criteria.py -v`
Expected: PASS（7件）

- [ ] **Step 5: Commit**

```bash
cd /Users/wadaatsushi/Documents/automation/marketar/research-tool
sed -i '' 's/^version = "0.5.4"/version = "0.6.0"/' pyproject.toml
git add src/domain/value_objects/discovery_criteria.py src/tests/test_discovery_criteria.py pyproject.toml
git commit -m "feat: Keepa Product Finder の抽出条件を値オブジェクトにした v0.6.0"
```

---

### Task 2: Keepa Product Finder の呼び出し

**Files:**
- Modify: `src/infrastructure/keepa_client.py`（`KeepaClient` にメソッドを追加。既存メソッドは変更しない）
- Test: `src/tests/test_keepa_find_asins.py`

**Interfaces:**
- Consumes: `DiscoveryCriteria.selection(now, page)`（Task 1）
- Produces: `KeepaClient.find_asins(self, criteria: DiscoveryCriteria, now: datetime, max_pages: int = 20) -> list[Asin]`

**注意:** 既存の `fetch_product` は `session.get` を使うが、Product Finder は **`session.post`**（`params` にキーとドメイン、`json` に selection）。既存の `FakeSession` は `get` しか持たないので、このテストは専用の Fake を書く。

- [ ] **Step 1: Write the failing test**

`src/tests/test_keepa_find_asins.py`:

```python
from datetime import datetime, timezone

import pytest

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
from src.infrastructure.keepa_client import KeepaApiError, KeepaClient

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakePostSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def post(self, url: str, params: dict, json: dict, timeout: int) -> FakeResponse:
        self.calls.append(json)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


def _client(session: FakePostSession) -> KeepaClient:
    return KeepaClient("dummy-key", session=session, sleep=lambda seconds: None)


class TestFindAsins:
    def test_1ページで収まるなら1回で終わる(self) -> None:
        session = FakePostSession(
            [FakeResponse(200, {"asinList": ["B000000001", "B000000002"], "totalResults": 2})]
        )

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001", "B000000002"]
        assert len(session.calls) == 1

    def test_総件数に達するまでページを進める(self) -> None:
        first = FakeResponse(200, {"asinList": [f"B00000{n:04d}" for n in range(50)], "totalResults": 60})
        second = FakeResponse(200, {"asinList": [f"B00001{n:04d}" for n in range(10)], "totalResults": 60})
        session = FakePostSession([first, second])

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert len(asins) == 60
        assert [call["page"] for call in session.calls] == [0, 1]

    def test_空ページが返ったら打ち切る(self) -> None:
        first = FakeResponse(200, {"asinList": [f"B00000{n:04d}" for n in range(50)], "totalResults": 999})
        empty = FakeResponse(200, {"asinList": [], "totalResults": 999})
        session = FakePostSession([first, empty])

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert len(asins) == 50
        assert len(session.calls) == 2

    def test_条件の誤りは即座に失敗させる(self) -> None:
        session = FakePostSession(
            [FakeResponse(400, {"error": {"message": "invalidParameter"}})]
        )

        with pytest.raises(KeepaApiError, match="400"):
            _client(session).find_asins(DiscoveryCriteria(), NOW)

    def test_トークン枯渇は待機してから再試行する(self) -> None:
        depleted = FakeResponse(429, {"tokensLeft": -5, "refillIn": 1000})
        ok = FakeResponse(200, {"asinList": ["B000000001"], "totalResults": 1})
        session = FakePostSession([depleted, ok])
        slept: list[float] = []
        client = KeepaClient("dummy-key", session=session, sleep=slept.append)

        asins = client.find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001"]
        assert slept == [1.0]

    def test_解釈できないASINは落とす(self) -> None:
        session = FakePostSession(
            [FakeResponse(200, {"asinList": ["B000000001", "", "短い"], "totalResults": 3})]
        )

        asins = _client(session).find_asins(DiscoveryCriteria(), NOW)

        assert [str(asin) for asin in asins] == ["B000000001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/tests/test_keepa_find_asins.py -v`
Expected: FAIL（`AttributeError: 'KeepaClient' object has no attribute 'find_asins'`）

- [ ] **Step 3: Write minimal implementation**

`src/infrastructure/keepa_client.py` の import に追加:

```python
from datetime import datetime, timedelta, timezone  # datetime は既存。timedelta が無ければ足す

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
```

`KeepaClient` クラスに以下を追加（`fetch_refill_rate_per_minute` の後ろ）:

```python
    def find_asins(
        self,
        criteria: DiscoveryCriteria,
        now: datetime,
        max_pages: int = 20,
    ) -> list[Asin]:
        found: list[Asin] = []
        page = 0

        while page < max_pages:
            payload = self._query_page(criteria, now, page)
            raw_asins = payload.get("asinList") or []
            if not raw_asins:
                break

            found.extend(asin for asin in map(Asin.parse, raw_asins) if asin is not None)

            total = payload.get("totalResults") or 0
            if len(found) >= total:
                break
            page += 1

        logger.info(
            "Product Finder で候補を取得しました",
            extra={"context": {"count": len(found), "pages": page + 1}},
        )
        return found

    def _query_page(self, criteria: DiscoveryCriteria, now: datetime, page: int) -> dict:
        for attempt in range(MAX_TOKEN_RETRIES):
            response = self.session.post(
                f"{self.base_url}/query",
                params={"key": self.api_key, "domain": JAPAN_DOMAIN},
                json=criteria.selection(now, page=page),
                timeout=self.timeout,
            )
            payload = self._decode(response)
            self.tokens_left = payload.get("tokensLeft", self.tokens_left)

            if self._is_token_depleted(response, payload):
                self._wait_for_query_refill(payload, page, attempt)
                continue

            if response.status_code != 200:
                raise KeepaApiError(
                    f"Keepa Product Finder error: {response.status_code} - {response.text[:200]}"
                )

            return payload

        raise KeepaApiError(f"Keepa token exhausted after {MAX_TOKEN_RETRIES} retries: page={page}")

    def _wait_for_query_refill(self, payload: dict, page: int, attempt: int) -> None:
        refill_ms = payload.get("refillIn")
        seconds = (refill_ms / 1000) if refill_ms else DEFAULT_TOKEN_WAIT_SECONDS
        seconds = min(seconds, MAX_TOKEN_WAIT_SECONDS)

        logger.warning(
            "Product Finder のトークンが枯渇したため補充を待機",
            extra={
                "context": {
                    "page": page,
                    "wait_seconds": seconds,
                    "tokens_left": payload.get("tokensLeft"),
                    "attempt": attempt + 1,
                }
            },
        )
        self.sleep(seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/tests/test_keepa_find_asins.py src/tests/test_keepa_client.py src/tests/test_keepa_rate_limit.py -v`
Expected: PASS（新規6件 + 既存が全て通ること）

- [ ] **Step 5: Commit**

```bash
sed -i '' 's/^version = "0.6.0"/version = "0.6.1"/' pyproject.toml
git add src/infrastructure/keepa_client.py src/tests/test_keepa_find_asins.py pyproject.toml
git commit -m "feat: Keepa Product Finder を叩く find_asins を追加 v0.6.1"
```

---

### Task 3: 既知 ASIN との突合

**Files:**
- Create: `src/usecases/discover_products.py`
- Test: `src/tests/test_discover_products.py`

**Interfaces:**
- Consumes: `Asin.parse`（既存）、`ColumnCodes`（既存）
- Produces:
  - `DISCOVERY_SHEET: str = "自動調査"`
  - `known_asins(sheet_values: dict[str, list[list]]) -> set[str]`
  - `select_new_asins(found: list[Asin], known: set[str], limit: int | None = None) -> list[Asin]`

**注意:** ASIN 列には素の ASIN と商品URLが混在する。`Asin.parse()` を通してから比較する。ASIN 列コード（`ASIN_SELL`）を持たないタブ（プロンプト、テンプレ(新)など）は無視する。

- [ ] **Step 1: Write the failing test**

`src/tests/test_discover_products.py`:

```python
from src.domain.value_objects.asin import Asin
from src.usecases.discover_products import known_asins, select_new_asins

CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN"]
HEADER_2 = ["", "", "ASIN", "GTIN"]
HEADER_3 = ["0", "1", "", "JAN/EAN"]


def _sheet(asin_cells: list[str]) -> list[list]:
    return [CODE_ROW, HEADER_2, HEADER_3] + [["", "", cell, ""] for cell in asin_cells]


class TestKnownAsins:
    def test_素のASINを拾う(self) -> None:
        assert known_asins({"候補": _sheet(["B000000001"])}) == {"B000000001"}

    def test_商品URLも同じASINとして扱う(self) -> None:
        values = _sheet(["https://www.amazon.co.jp/dp/B000000002/ref=sr_1_3?th=1"])
        assert known_asins({"優先": values}) == {"B000000002"}

    def test_複数タブを合算する(self) -> None:
        sheets = {"候補": _sheet(["B000000001"]), "候補外": _sheet(["B000000003"])}
        assert known_asins(sheets) == {"B000000001", "B000000003"}

    def test_ASIN列コードが無いタブは無視する(self) -> None:
        values = [["んh", "MEMO"], ["", ""], ["", ""], ["", "B000000009"]]
        assert known_asins({"プロンプト": values}) == set()

    def test_解釈できないセルは無視する(self) -> None:
        assert known_asins({"候補": _sheet(["", "https://amzn.to/xxxx", "-"])}) == set()


class TestSelectNewAsins:
    def test_既知を除いた順序を保つ(self) -> None:
        found = [Asin("B000000001"), Asin("B000000002"), Asin("B000000003")]

        assert [str(a) for a in select_new_asins(found, {"B000000002"})] == [
            "B000000001",
            "B000000003",
        ]

    def test_同じASINが2回出ても1回にする(self) -> None:
        found = [Asin("B000000001"), Asin("B000000001")]
        assert [str(a) for a in select_new_asins(found, set())] == ["B000000001"]

    def test_上限で切る(self) -> None:
        found = [Asin("B000000001"), Asin("B000000002")]
        assert [str(a) for a in select_new_asins(found, set(), limit=1)] == ["B000000001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products.py -v`
Expected: FAIL（`ModuleNotFoundError: src.usecases.discover_products`）

- [ ] **Step 3: Write minimal implementation**

`src/usecases/discover_products.py`:

```python
from __future__ import annotations

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

DISCOVERY_SHEET = "自動調査"
ASIN_CODE = "ASIN_SELL"
DATA_START_ROW = 3


def known_asins(sheet_values: dict[str, list[list]]) -> set[str]:
    collected: set[str] = set()

    for values in sheet_values.values():
        asin_index = ColumnCodes(values).index_of(ASIN_CODE)
        if asin_index is None:
            continue

        for row in values[DATA_START_ROW:]:
            if asin_index >= len(row):
                continue
            asin = Asin.parse(row[asin_index])
            if asin is not None:
                collected.add(str(asin))

    return collected


def select_new_asins(
    found: list[Asin], known: set[str], limit: int | None = None
) -> list[Asin]:
    selected: list[Asin] = []
    seen = set(known)

    for asin in found:
        if str(asin) in seen:
            continue
        seen.add(str(asin))
        selected.append(asin)
        if limit is not None and len(selected) >= limit:
            break

    return selected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products.py -v`
Expected: PASS（8件）

- [ ] **Step 5: Commit**

```bash
sed -i '' 's/^version = "0.6.1"/version = "0.6.2"/' pyproject.toml
git add src/usecases/discover_products.py src/tests/test_discover_products.py pyproject.toml
git commit -m "feat: 発見したASINを全タブの既知ASINと突合する v0.6.2"
```

---

### Task 4: 自動調査タブへの追記計画

**Files:**
- Modify: `src/usecases/discover_products.py`（Task 3 で作ったファイルに追加）
- Modify: `src/infrastructure/sheet_repository.py`（`read_values` と `ensure_rows` を追加）
- Test: `src/tests/test_discover_products.py`（Task 3 のファイルに追加）

**Interfaces:**
- Consumes: `known_asins` / `select_new_asins`（Task 3）、`GoogleSheetRepository.apply_updates`（既存）
- Produces:
  - `NOTE_CODE: str = "NOTE_BUY_OTHER2"`
  - `AppendPlan(updates: dict[int, dict[int, object]], rows_to_add: int)`
  - `plan_append(values: list[list], asins: list[Asin], discovered_on: date) -> AppendPlan`
  - `GoogleSheetRepository.read_values(self, sheet_name: str) -> list[list]`
  - `GoogleSheetRepository.ensure_rows(self, sheet_name: str, last_row_number: int) -> int`

**注意:** 備考は `自動調査YYYY-MM-DD` の形式。自動調査タブは70行しかないので、書き込み先の行番号がシートの行数を超えるときは先に行を足す。

- [ ] **Step 1: Write the failing test**

`src/tests/test_discover_products.py` の末尾に追加:

```python
from datetime import date

from src.usecases.discover_products import plan_append

APPEND_CODE_ROW = ["んh", "CHECK2", "ASIN_SELL", "JAN", "UPC", "IMAGE", "TITLE_SELL",
                   "TITLE_BUY", "NOTE_BUY_OTHER8", "NOTE_BUY_OTHER7", "", "NOTE_BUY_OTHER2"]
DISCOVERED_ON = date(2026, 8, 29)


def _append_sheet(existing: list[str]) -> list[list]:
    filler = ["", "", "", "", "", "", "", "", "", ""]
    header = [APPEND_CODE_ROW, ["", "", "ASIN"] + filler, ["0", "1", ""] + filler]
    return header + [["", "", cell] + filler for cell in existing]


class TestPlanAppend:
    def test_空行にASINと備考を書く(self) -> None:
        plan = plan_append(_append_sheet(["B000000001", "", ""]), [Asin("B000000009")], DISCOVERED_ON)

        assert plan.updates == {5: {2: "B000000009", 11: "自動調査2026-08-29"}}
        assert plan.rows_to_add == 0

    def test_空行を上から順に使う(self) -> None:
        asins = [Asin("B000000009"), Asin("B000000008")]

        plan = plan_append(_append_sheet(["B000000001", "", ""]), asins, DISCOVERED_ON)

        assert sorted(plan.updates) == [5, 6]
        assert plan.updates[6][2] == "B000000008"

    def test_空行が足りなければ行を足す(self) -> None:
        asins = [Asin("B000000009"), Asin("B000000008")]

        plan = plan_append(_append_sheet(["B000000001"]), asins, DISCOVERED_ON)

        assert sorted(plan.updates) == [5, 6]
        assert plan.rows_to_add == 2

    def test_列は列コードで引く(self) -> None:
        moved = [["んh", "ASIN_SELL", "NOTE_BUY_OTHER2"], ["", "ASIN", "備考"], ["0", "", ""], ["", "", ""]]

        plan = plan_append(moved, [Asin("B000000009")], DISCOVERED_ON)

        assert plan.updates == {4: {1: "B000000009", 2: "自動調査2026-08-29"}}

    def test_ASINが無ければ何も書かない(self) -> None:
        plan = plan_append(_append_sheet(["", ""]), [], DISCOVERED_ON)

        assert plan.updates == {}
        assert plan.rows_to_add == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products.py -k PlanAppend -v`
Expected: FAIL（`ImportError: cannot import name 'plan_append'`）

- [ ] **Step 3: Write minimal implementation**

`src/usecases/discover_products.py` に追加:

```python
from dataclasses import dataclass
from datetime import date

NOTE_CODE = "NOTE_BUY_OTHER2"
NOTE_PREFIX = "自動調査"


@dataclass(frozen=True)
class AppendPlan:
    updates: dict[int, dict[int, object]]
    rows_to_add: int


def _is_blank(row: list, index: int) -> bool:
    return index >= len(row) or not str(row[index]).strip()


def plan_append(values: list[list], asins: list[Asin], discovered_on: date) -> AppendPlan:
    if not asins:
        return AppendPlan(updates={}, rows_to_add=0)

    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    note_index = codes.index_of(NOTE_CODE)
    if asin_index is None or note_index is None:
        raise ValueError(f"1行目に列コードが見つかりません: {ASIN_CODE} / {NOTE_CODE}")

    note = f"{NOTE_PREFIX}{discovered_on.isoformat()}"
    blank_rows = [
        DATA_START_ROW + offset + 1
        for offset, row in enumerate(values[DATA_START_ROW:])
        if _is_blank(row, asin_index)
    ]

    updates: dict[int, dict[int, object]] = {}
    next_row = len(values) + 1
    rows_to_add = 0

    for position, asin in enumerate(asins):
        if position < len(blank_rows):
            row_number = blank_rows[position]
        else:
            row_number = next_row
            next_row += 1
            rows_to_add += 1
        updates[row_number] = {asin_index: str(asin), note_index: note}

    return AppendPlan(updates=updates, rows_to_add=rows_to_add)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products.py -v`
Expected: PASS（13件）

- [ ] **Step 5: Repository に読み書きの入口を足す**

`src/infrastructure/sheet_repository.py` の `GoogleSheetRepository` に追加:

```python
    def read_values(self, sheet_name: str) -> list[list]:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        return worksheet.get_values(value_render_option=FORMULA_RENDER_OPTION)

    def ensure_rows(self, sheet_name: str, last_row_number: int) -> int:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        shortage = last_row_number - worksheet.row_count
        if shortage <= 0:
            return 0

        worksheet.add_rows(shortage)
        logger.info(
            "行を追加しました",
            extra={"context": {"sheet": sheet_name, "added": shortage}},
        )
        return shortage
```

- [ ] **Step 6: Commit**

```bash
sed -i '' 's/^version = "0.6.2"/version = "0.7.0"/' pyproject.toml
git add src/usecases/discover_products.py src/infrastructure/sheet_repository.py src/tests/test_discover_products.py pyproject.toml
git commit -m "feat: 自動調査タブへASINと発見日を追記する計画を組む v0.7.0"
```

---

### Task 5: CLI

**Files:**
- Create: `discover_products.py`（リポジトリ直下。`find_supplier.py` と同じ位置）
- Test: `src/tests/test_discover_products_cli.py`

**Interfaces:**
- Consumes: Task 1〜4 の全て
- Produces:
  - `run(args: argparse.Namespace) -> int`
  - `fetch_command(sheet: str) -> list[str]`

**引数:**

| 引数 | 既定 | 意味 |
|---|---|---|
| `--limit` | なし | 追記する件数の上限 |
| `--dry-run` | false | 書き込まず件数と ASIN を表示する |
| `--no-fetch` | false | 追記だけで `fetch_products.py` を呼ばない |
| `--debug` | false | DEBUG ログを出す |

- [ ] **Step 1: Write the failing test**

`src/tests/test_discover_products_cli.py`:

```python
import sys

from discover_products import fetch_command


class TestFetchCommand:
    def test_同じvenvのpythonでfetch_productsを呼ぶ(self) -> None:
        command = fetch_command("自動調査")

        assert command[0] == sys.executable
        assert command[1].endswith("fetch_products.py")
        assert command[2:] == ["--sheet", "自動調査"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products_cli.py -v`
Expected: FAIL（`ModuleNotFoundError: discover_products`）

- [ ] **Step 3: Write minimal implementation**

`discover_products.py`:

```python
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.discover_products import (
    DISCOVERY_SHEET,
    known_asins,
    plan_append,
    select_new_asins,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("discover_products")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keepaで発売半年以内・月販1000個以上・1000円以下の商品を探し自動調査タブへ積む"
    )
    parser.add_argument("--limit", type=int, help="追記する件数の上限")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず件数だけ表示する")
    parser.add_argument("--no-fetch", action="store_true", help="商品情報の取得を続けて行わない")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    load_dotenv(PROJECT_ROOT / ".env")
    return GoogleSheetRepository(
        str(PROJECT_ROOT / os.environ["SERVICE_ACCOUNT_FILE"]),
        os.environ["RESEARCH_SPREADSHEET_ID"],
    )


def fetch_command(sheet: str) -> list[str]:
    return [sys.executable, str(PROJECT_ROOT / "fetch_products.py"), "--sheet", sheet]


def collect_known(repository: GoogleSheetRepository) -> set[str]:
    sheets = {title: repository.read_values(title) for title in repository.sheet_titles()}
    return known_asins(sheets)


def run(args: argparse.Namespace) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    keepa = KeepaClient(os.environ["KEEPA_API_KEY"])

    found = keepa.find_asins(DiscoveryCriteria(), datetime.now(timezone.utc))
    repository = build_repository()
    fresh = select_new_asins(found, collect_known(repository), limit=args.limit)

    logger.info(
        "発見しました",
        extra={"context": {"found": len(found), "new": len(fresh)}},
    )
    for asin in fresh:
        print(f"{asin} {asin.amazon_url}")

    if not fresh or args.dry_run:
        return 0

    values = repository.read_values(DISCOVERY_SHEET)
    plan = plan_append(values, fresh, date.today())
    if plan.rows_to_add:
        repository.ensure_rows(DISCOVERY_SHEET, max(plan.updates))
    written = repository.apply_updates(DISCOVERY_SHEET, plan.updates)

    logger.info(
        "自動調査タブへ追記しました",
        extra={"context": {"cells": written, "rows": len(plan.updates)}},
    )

    if args.no_fetch:
        return 0
    return subprocess.run(fetch_command(DISCOVERY_SHEET), cwd=PROJECT_ROOT, check=False).returncode


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest src/tests/test_discover_products_cli.py -v`
Expected: PASS（1件）

- [ ] **Step 5: 全テストを通す**

Run: `.venv/bin/python -m pytest -q`
Expected: 既存を含め全て PASS

- [ ] **Step 6: 実機で dry-run する**

Run: `.venv/bin/python discover_products.py --dry-run`
Expected: 発見件数と未知の ASIN 一覧が出て、シートは書き換わらない。2026-08-29 の実測は 62件。

- [ ] **Step 7: 実機で 3件だけ書く**

Run: `.venv/bin/python discover_products.py --limit 3 --no-fetch`
Expected: 自動調査タブの C列に3件、L列に `自動調査YYYY-MM-DD` が入る。**シートを目視で確認する。**

- [ ] **Step 8: Commit**

```bash
sed -i '' 's/^version = "0.7.0"/version = "0.8.0"/' pyproject.toml
git add discover_products.py src/tests/test_discover_products_cli.py pyproject.toml
git commit -m "feat: 売れ筋新商品を自動調査タブへ積むCLIを追加 v0.8.0"
```

---

### Task 6: コマンド手順書

**Files:**
- Create: `.claude/commands/market-research.md`
- Modify: `CLAUDE.md`（「仕入先探し（1688）」の節の後ろに「売れ筋新商品の発見」を追加）

**Interfaces:**
- Consumes: Task 5 の CLI
- Produces: なし（ドキュメント）

- [ ] **Step 1: 手順書を書く**

`.claude/commands/market-research.md` に次を含める。

- 何をするコマンドか（1行）
- 実行例（`--dry-run` → `--limit` → 本番の順）
- 抽出条件の表（spec からコピー。閾値を変えるときは `DiscoveryCriteria` を触ると明記）
- **Keepa の落とし穴3点**: `releaseDate` は使えない / Amazon除外は `availabilityAmazon` / `perPage` は50以上
- 突合対象に「候補外」を含めていること（一度落とした商品を再掲しないため）
- 見つかった ASIN は `https://www.amazon.co.jp/dp/<ASIN>` のリンクで報告すること（親リポジトリの規約）
- 0件は正常。条件が厳しすぎるときに緩める順序（月販 → 価格 → 日数）

- [ ] **Step 2: CLAUDE.md へ追記**

`## 売れ筋新商品の発見（Keepa Product Finder）` の節を作り、次の3点だけ書く。

```markdown
## 売れ筋新商品の発見（Keepa Product Finder）

`discover_products.py` が条件に合う ASIN を「自動調査」タブへ積む。手順は `/market-research`。

- **`releaseDate` は 0 の商品が大半で使えない。** 発売日の判定は `listedSince`（Amazon 出品日）
- **Amazon 本体の除外は `availabilityAmazon: [-1]`。** `current_AMAZON` の範囲指定は 0件になる
- **`perPage` は 50 未満だと 400 エラー。** 1回 11トークン
```

- [ ] **Step 3: Commit**

```bash
sed -i '' 's/^version = "0.8.0"/version = "0.8.1"/' pyproject.toml
git add .claude/commands/market-research.md CLAUDE.md pyproject.toml
git commit -m "docs: /market-research の手順と Keepa の落とし穴を記録 v0.8.1"
```

---

### Task 7: 定期実行

**Files:**
- Create: `/Users/wadaatsushi/Documents/automation/ops/launchd/com.wada.market-research.plist`
- Test: `cd /Users/wadaatsushi/Documents/automation/ops && python3 check_launchd.py`

**Interfaces:**
- Consumes: Task 5 の CLI
- Produces: launchd ジョブ `com.wada.market-research`

**注意（親リポジトリの TCC 制約）:**
- plist は `ops/launchd/` を正本にし、`sync_agents.py` が `~/Library/LaunchAgents/` へ**実ファイルとして cp する**。symlink にしない
- `ProgramArguments[0]` は `~/Library/LaunchAgents/scripts/notify-on-failure.sh`
- `StandardOutPath` / `StandardErrorPath` は `~/Library/Logs/` の**絶対パス**（`~` は展開されない）
- **シェルからの手動実行は検証にならない。** `launchctl print` の `runs` と `last exit code` で確認する

- [ ] **Step 1: plist を書く**

`com.automation.category-rank.plist` を雛形にして次を変える。

- `Label` → `com.wada.market-research`
- `WorkingDirectory` → `/Users/wadaatsushi/Documents/automation/marketar/research-tool`
- `StandardOutPath` → `/Users/wadaatsushi/Library/Logs/market-research.log`
- `StandardErrorPath` → `/Users/wadaatsushi/Library/Logs/market-research.err`
- `StartCalendarInterval` → `Hour 6` / `Minute 30`
- 実行コマンド → `.venv/bin/python discover_products.py`（`com.automation.download-amazon-data.plist` が同じ形）

- [ ] **Step 2: 配布して検査する**

```bash
cd /Users/wadaatsushi/Documents/automation/ops
python3 sync_agents.py
python3 check_launchd.py
```

Expected: `check_launchd.py` が exit 0。symlink 混入・未ロードの指摘が出ないこと。

- [ ] **Step 3: 手動で1回起動して結果を確認する**

```bash
launchctl kickstart -k gui/$(id -u)/com.wada.market-research
sleep 60
launchctl print gui/$(id -u)/com.wada.market-research | grep -E "runs|last exit code"
tail -20 ~/Library/Logs/market-research.log
```

Expected: `runs` が 1 以上、`last exit code = 0`。ログに発見件数が出ていること。

- [ ] **Step 4: Commit**

plist は**親リポジトリ（automation 本体）**にある。research-tool ではないので別コミットになる。

```bash
cd /Users/wadaatsushi/Documents/automation
git add ops/launchd/com.wada.market-research.plist
git diff --cached --name-only   # 自分の担当範囲外が0件であることを確認する
git commit -m "feat(ops): 売れ筋新商品の自動発見を毎日06:30に実行する"
```

---

## Self-Review

**Spec coverage**

| spec の要求 | 対応 |
|---|---|
| 抽出条件（価格・月販・listedSince・productType・availabilityAmazon・除外18カテゴリ・sort・perPage） | Task 1 |
| ページング、400 は即停止、トークン枯渇待ち | Task 2 |
| ASIN 列を持つ全タブとの突合、URL 混在への対応、候補外も含める | Task 3 |
| C列に ASIN・L列に `自動調査YYYY-MM-DD`、列コードで引く、行が足りなければ追加、`batch_update` 1回 | Task 4 |
| 発見 → 追記 → `fetch_products.py` の連結、`--dry-run` | Task 5 |
| 0件は正常として終了 | Task 5（`fresh` が空なら 0 を返す） |
| 手順書と CLAUDE.md への記録 | Task 6 |
| 毎日 06:30 の launchd、TCC 制約 | Task 7 |

**Type consistency**

- `DiscoveryCriteria.selection(now, page)` は Task 1 で定義し、Task 2 の `_query_page` から同じ引数で呼ぶ
- `known_asins` は `dict[str, list[list]]` を取り `set[str]` を返す。Task 5 の `collect_known` が同じ形で渡す
- `plan_append` の戻りは `AppendPlan(updates, rows_to_add)`。Task 5 は `plan.updates` と `plan.rows_to_add` を使う
- `Asin` は `__str__` で素の ASIN を返し、`amazon_url` プロパティを持つ（既存）

**確認済み（2026-08-29）**

- `configure_logging(level: int = logging.INFO)` — 計画中の `configure_logging(logging.DEBUG if args.debug else logging.INFO)` はそのまま使える
- `gspread 6.2.1` に `Worksheet.add_rows(rows: int)` と `row_count` がある — Task 4 の `ensure_rows` はそのまま動く
