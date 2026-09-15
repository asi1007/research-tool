# /rival-metrics

競合ASINに**月販・価格・レビュー数・評価**を付けて、どれが強敵でどこが空いているかを出す。

**有料ツールを使わない。** セラースプライトや Jungle Scout の類は要らない。
すべて既に契約済みの Keepa と、無料の Amazon 公式API（SP-API / Ads API）だけで足りる。

## 何がタダで取れるか

| 欲しいもの | 取り方 | 費用 |
|---|---|---|
| 月販数・価格・レビュー数・評価・ランキング | **Keepa** `/product`（`rival_metrics.py`） | 契約済み。1ASIN 1トークン |
| 競合ASINの一覧（広告の商品ターゲティング候補） | **Ads API** `/sp/targets/products/recommendations`（`ad/tools/launch_probe.py`） | **無料** |
| 推奨キーワードと入札額 | **Ads API** `/sp/targets/keywords/recommendations`（同上／`fill_keywords.py`） | **無料** |
| 検索順位（`searchFrequencyRank`） | **Brand Analytics** 検索キーワードレポート（`fill_search_rank.py`） | **無料**（ブランド登録者） |
| 箇条書き・A+・バリエーション・画像 | **playwright**（`listing-creator/probe_competitor.py`） | 無料 |
| 同一カテゴリの競合発見 | **playwright**（`rival_research.py collect`） | 無料 |
| 手数料・カート価格 | **SP-API** | 無料 |

**唯一タダで取れないのが検索ボリューム（検索数）。** 公式APIに存在しない。
代わりに Brand Analytics の `searchFrequencyRank`（検索**順位**）を使う。順位が上なら検索数も多い。
リサーチシートのN列「検索数」がセラースプライトの手入力のまま残っているのはこのため。

## 手順

```bash
# 1. 競合ASINを集める（広告の商品ターゲティング候補が一番早い。100件返る）
cd /Users/wadaatsushi/Documents/automation/marketar/ad
.venv/bin/python tools/launch_probe.py <ASIN> --sku <ASIN>=<SKU> > /tmp/probe.txt

# 2. 月販・価格・レビューを付ける（ASINを拾って Keepa へ）
cd /Users/wadaatsushi/Documents/automation/marketar/research-tool
sed -n '/商品ターゲティング/,$p' /tmp/probe.txt | .venv/bin/python rival_metrics.py --limit 20
```

ASIN を直接並べてもよい。`--json` で機械可読。

```bash
.venv/bin/python rival_metrics.py B08L4NBGRC B09FP58BNX --json
```

## 読み方

月商（月販 × 価格）の大きい順に並ぶ。**月販が取れない行は末尾へ回る**（比較できないため）。

| 強さ | 条件 | 意味 |
|---|---|---|
| **強敵** | レビュー200件以上 | 価格勝負になる。同じ土俵に乗らない |
| **狙い目** | レビュー50件以下 かつ 月販30以上 | 売れているのにレビューが薄い。後発でも入れる |
| **小粒** | 月販30未満 | 広告のターゲットにしても意味がない |
| **不明** | 月販が取れない／レビューが中間 | Keepa が推定できていない。件数が多いなら母数として見る |

**レビュー数は同じ値が並ぶことがある。** バリエーション違いの子ASINはレビューが親で
集約されるため（例: 1013件が3行に出る）。**別商品として数えない。**

## Keepa は `rating=1` を付けないとレビューが返らない

`/product` の既定ではレビュー数も評価も `-1`（データなし）で返る。

```
&stats=1&history=0&rating=1
```

`rating=1` を落とすと「レビュー0件の新商品ばかり」という誤った絵になる。**必ず付ける。**

## 価格は円そのまま。100で割らない

日本（domain=5）の Keepa 価格は**円が整数でそのまま**入っている。
米国のようにセント単位ではないので、`1万円以上なら100で割る` のような補正を入れてはいけない。
25,800円の商品が258円になる。

| index | 中身 |
|---|---|
| 1 | New |
| 3 | ランキング |
| 16 | 評価（**10倍値**。40 = 4.0） |
| 17 | レビュー数 |
| 18 | カート価格 |

カート価格が `-1` の商品は珍しくない。その場合は New を使う。

## トークンを使い切らない

Keepa は 1ASIN 1トークン、補充 5/分。**100ASINを引くと100トークン**消える。
`launch_probe.py` の候補は100件返るので、全部引くと残高が一気に減る。

- 上位だけ見るなら `head -60` などで絞ってから流す
- 残高は実行時のログ（`tokens_left`）に出る
- マイナス残高になりうる。市場調査（`/market-research`）と同じ日に大量に引かない

## 注意

- **ASINはどこから貼ってもよい。** 標準入力から `B0` で始まる10桁を正規表現で拾うので、
  `launch_probe.py` の出力でも、Amazonの検索結果をコピペしたものでも通る
- 重複ASINは1件にまとめる
- `--limit` の既定は20。母集団の中央値は**絞る前の全件**ではなく表示分で出る
