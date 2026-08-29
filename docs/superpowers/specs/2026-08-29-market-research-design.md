# 売れ筋新商品の自動発見（/market-research）

2026-08-29

## 目的

Keepa Product Finder で **発売半年以内・月販1000個以上・1000円以下** の商品を機械的に洗い出し、
リサーチシートの「自動調査」タブ（gid=728003366）へ ASIN を積む。

現在のリサーチは競合URLを人が持ち込むところから始まる。**ASIN を見つける経路がリポジトリに無い**
ため、母集団が人の目に依存している。ここを埋める。

既存の `fetch_products.py` は「ASIN を与えると埋める」ツールなので**そのまま流用する**。
本機能が作るのは ASIN の供給側だけ。

## 前提（実機で確認した Keepa の仕様）

2026-08-29 に `api.keepa.com` へ実際に投げて確認した。公式ドキュメントの記述と食い違う点がある。

### エンドポイントとトークン

```
POST https://api.keepa.com/query?key=<KEY>&domain=5
body: selection の JSON
```

- **1回 11トークン**（`tokensConsumed: 11`）。上限300・補充5/分の契約なので日に数回なら問題ない
- 戻りは `asinList`（最大 `perPage` 件）と `totalResults`
- **`perPage` は 50 未満だと 400 エラー**（`combination of perPage and page exeeds limit or is too small`）。
  10 を指定して落ちた。50 以上にする

### 発売日は `releaseDate` では取れない

`releaseDate` は **0 の商品が大半**。サンプル `B0GM7HHB91` も 0 だった。

**`listedSince`（Amazon に出品された日、Keepa minutes）を使う。** 同じ商品で 2026-03-11 が入っており、
半年以内の判定に使える。`trackingSince`（Keepa が追跡を始めた日）とは2日ずれるので混同しない。

Keepa minutes は `2011-01-01T00:00:00Z` からの経過分。

### Amazon 本体の除外は `availabilityAmazon`

**`current_AMAZON` での範囲指定は使えない。** `current_AMAZON_lte: -1` は 0件になる
（-1 は「在庫なし」を表す番兵で、価格の範囲比較の対象外）。

```
"availabilityAmazon": [-1]     ← Amazon の出品が存在しない商品だけが残る
```

### 価格は円そのまま

日本ドメインの `current_NEW` は円の整数（サンプルは `965` = 965円）。セント換算は不要。

### 段階ごとの件数（2026-08-29 実測）

| 条件 | 件数 |
|---|---|
| 3条件のみ（半年・月販1000・1000円以下） | 202 |
| ＋ Amazon本体を除外 | 88 |
| ＋ 除外カテゴリ 18 | **62** |

## 抽出条件

```json
{
  "current_NEW_gte": 1,
  "current_NEW_lte": 1000,
  "monthlySold_gte": 1000,
  "listedSince_gte": "<180日前の Keepa minutes>",
  "productType": [0],
  "availabilityAmazon": [-1],
  "categories_exclude": [...18件],
  "sort": [["monthlySold", "desc"]],
  "perPage": 50,
  "page": 0
}
```

`productType: [0]` は標準商品のみ。**バリエーション親（5）と電子書籍（2）を落とす。**

### 除外するルートカテゴリ（18）

| ID | 名称 | 理由 |
|---|---|---|
| 465392 | 本 | 中国輸入の対象外 |
| 52033011 | 洋書 | 同上 |
| 561956 | ミュージック | 同上 |
| 561958 | DVD | 同上 |
| 2128134051 | デジタルミュージック | 同上 |
| 2250738051 | Kindleストア | 同上 |
| 2351649051 | Prime Video | 同上 |
| 2381130051 | アプリ＆ゲーム | 同上 |
| 4788676051 | Alexaスキル | 同上 |
| 637392 | PCソフト | 同上 |
| 637394 | ゲーム | 同上 |
| 2320455051 | ファイナンス | 同上 |
| 4976279051 | Amazonデバイス・アクセサリ | 純正品のみ |
| 160384011 | ドラッグストア | 薬機法 |
| 57239051 | 食品・飲料・お酒 | 食品衛生法 |
| 344845011 | ベビー＆マタニティ | 安全基準 |
| 2277724051 | 大型家電 | 送料で採算が合わない |
| 3210981 | 家電＆カメラ | PSE |

**残すのは13カテゴリ。** ビューティー（52374051）とパソコン・周辺機器（2127209051）は
メイクブラシ・コスメ小物・ケーブル類が中国輸入の定番なので**残す**。

閾値とIDは `DiscoveryCriteria` に集約し、変えるときは1箇所だけ触る。

## 構成

```
discover_products.py（CLI）
  └ usecases/DiscoverProductsUseCase
      ├ KeepaClient.find_asins(criteria)        → 条件に合う ASIN
      ├ GoogleSheetRepository.collect_known_asins()  → 全タブの既知 ASIN
      └ GoogleSheetRepository.append_discovered()    → 自動調査タブへ追記
```

| 追加 | 責務 |
|---|---|
| `domain/value_objects/discovery_criteria.py` | 条件を持ち、Keepa の `selection` dict を作る。日付→Keepa minutes 変換もここ |
| `KeepaClient.find_asins()` | `/query` を叩き、`totalResults` を見てページングする。トークン枯渇時の待機は既存の `_wait_for_refill` を流用 |
| `usecases/discover_products.py` | 発見 → 突合 → 追記の順に呼ぶだけ。判断を持たない |
| `GoogleSheetRepository.collect_known_asins()` | ASIN 列を持つ全タブを読み、`Asin.parse()` で正規化した集合を返す |
| `GoogleSheetRepository.append_discovered()` | 自動調査タブの空行へ ASIN と備考を書く |
| `discover_products.py` | 引数処理と後続の `fetch_products` 呼び出し |
| `.claude/commands/market-research.md` | 手順と判断基準 |

## データフロー

1. `DiscoveryCriteria` から `selection` を組む
2. `find_asins()` が 50件ずつ取り、`totalResults` に達するまでページを進める
3. ASIN 列を持つ全タブの ASIN を集めて既知集合を作る
4. 差集合（未知の ASIN）だけを残す
5. 自動調査タブへ追記する
6. `fetch_products.py --sheet 自動調査` を呼んで商品情報を埋める

### 重複排除は全タブと突合する

対象は「リリース」「優先」「候補」「リサーチ700円以下」「自動調査」「1000円周辺」「単価1500~」
「単価2000~」「ハードル高い」「季節商品」「候補外」ほか、ASIN 列を持つ全タブ。

**ASIN 列には素の ASIN と商品URLが混在している。** 既存の `Asin.parse()` が両方を解釈するので
それを通してから集合に入れる。`amzn.to` の短縮URLは解釈できず `None` になるが、
その行は突合から漏れるだけで害はない。

「候補外」を突合対象に含めるのは、**一度落とした商品を毎回また拾わないため。**

### 書き込み

| 列コード | 列 | 値 |
|---|---|---|
| `ASIN_SELL` | C | 素の ASIN |
| `NOTE_BUY_OTHER2` | L（備考） | `自動調査YYYY-MM-DD` |

**列位置は固定しない。** 1行目の列コードを `ColumnCodes` で引く（親リポジトリの規約）。

書き込みは `batch_update` で1回にまとめる（gspread の 60req/min 制限）。
自動調査タブは 70行しかないので、**空行が足りなければ行を追加してから書く。**

## エラー処理

- Keepa が 400 を返したら条件の組み立て誤りなので**即座に止める**。再試行しない
- トークン枯渇（429 / `tokensLeft < 0`）は既存の待機処理に任せる
- Sheets の 503 は `find_supplier` と同じ問題を起こす。**追記は1回の `batch_update` で行い、
  失敗したら何も書かれていない状態にする**（部分書き込みによる歯抜けを避ける）
- 0件は正常。ログに残して終了する

## 定期実行

`com.wada.market-research` を毎日 06:30 に実行する。plist とラッパーの正本は `ops/launchd/`
に置き、`sync_agents.py` で配る（親リポジトリの TCC 制約に従う）。

06:30 は Keepa を使う他ジョブと重ならない枠。イーウー注文状況の取得（06:00）の後、
広告日次レポート（07:30）の前。

## テスト

pytest。Keepa と Sheets はモックする。

| 対象 | 検証すること |
|---|---|
| `DiscoveryCriteria` | `selection` のキーと値。180日前が Keepa minutes に正しく変換されること |
| `KeepaClient.find_asins` | ページング（`totalResults` 120 なら3回呼ぶ）、`perPage` が 50 以上であること |
| 突合 | URL 形式の既知 ASIN が素の ASIN と同一視されること、候補外タブも効くこと |
| 追記 | 列コードで列を引くこと、備考の書式、空行が無いとき行を追加すること |

実 API での疎通は 2026-08-29 に確認済み（62件）。

## やらないこと

- **Product Finder の戻り値から商品情報を埋めること。** 取得経路が2本になる。`fetch_products.py` に任せる
- **条件のシート側からの変更。** 閾値は `DiscoveryCriteria` に置く。UI を作らない
- **仕入先の自動探索との連結。** `/find-supplier` はキャプチャのため無人実行できない。別工程のまま
