# /market-research

Keepa Product Finder で「安い・売れてる・出たばかり」の商品を探し、未知の ASIN だけを「自動調査」タブへ積む。続けて `fetch_products.py` を呼び、商品情報まで埋める。

## 実行

```bash
.venv/bin/python discover_products.py --dry-run          # まず件数だけ見る（書き込まない）
.venv/bin/python discover_products.py --limit 3           # 少数だけ試しに書き込む
.venv/bin/python discover_products.py                      # 本番（上限なし、fetch_products.py まで実行）
```

- `--no-fetch` … 「自動調査」タブへ書くところで止める（`fetch_products.py` を呼ばない）
- `--debug` … DEBUG ログを出す

`--dry-run` は発見件数と ASIN 一覧を表示するだけで、シートには一切書き込まない。件数感を先に見てから `--limit` を決めること。

## 抽出条件（`DiscoveryCriteria`）

閾値を変えるときは `src/domain/value_objects/discovery_criteria.py` の `DiscoveryCriteria` を触る。ここ1箇所に集約してある。

| 条件 | 値 |
|---|---|
| 価格（`current_NEW`） | 1〜1000円 |
| 月間販売数（`monthlySold_gte`） | 1000個以上 |
| 出品からの経過（`listedSince_gte`） | 180日以内 |
| 商品タイプ（`productType`） | `[0]`（標準品のみ） |
| Amazon本体の出品（`availabilityAmazon`） | `[-1]`（本体が売っていないもの） |
| 除外カテゴリ（`categories_exclude`） | 18カテゴリ（本・DVD・食品・ベビー用品など中国輸入で扱えないもの） |
| 並び順 | `monthlySold` 降順 |
| `perPage` | 50 |

**実測値（2026-08-29）**: 条件のみで202件 → Amazon本体の出品を除外して88件 → 除外カテゴリを引いて62件。CLI の実機実行では発見59件・うち未知58件、`--limit 3` で3件を書き込み確認済み。

## Keepa の落とし穴（知らないと必ず詰まる）

1. **`releaseDate` は使えない。** 発売日が入っている商品はごく一部で、大半は 0 が返る。「出たばかり」の判定は `listedSince`（Amazon への出品日）を使う
2. **Amazon本体の除外は `availabilityAmazon: [-1]`。** `current_AMAZON` を範囲指定（例: `current_AMAZON_gte/lte`）で除外しようとすると **0件になる**。`-1`（出品なし）は範囲比較の対象外の値のため
3. **`perPage` は50未満だと400エラー**（`combination of perPage and page exeeds limit or is too small`）。1回のクエリで11トークン消費する

## 突合の仕様

- 既知 ASIN の判定は、ASIN 列（`ASIN_SELL`）を持つ**全タブ**を `values_batch_get` で1回に読んで突合する。タブごとに読むと Sheets の読み取りクォータ（429）に当たる（開発中に実際に踏んだ）
- **「候補外」タブも突合対象に含めている。** 一度落とした商品を再び「自動調査」タブへ積まないため
- 書き込み先は C列（`ASIN_SELL`）に ASIN、L列（`NOTE_BUY_OTHER2`）に `自動調査YYYY-MM-DD`

## 結果の報告

見つかった ASIN は `https://www.amazon.co.jp/dp/<ASIN>` のリンクで報告する（親リポジトリの規約）。

## 0件は正常

条件に合う商品が無ければ0件で終わる。エラーではない。条件が厳しすぎると疑う場合は、次の順で緩める。

1. 月販（`min_monthly_sold`）を下げる
2. 価格（`max_price_yen`）の上限を上げる
3. 経過日数（`max_age_days`）を伸ばす
