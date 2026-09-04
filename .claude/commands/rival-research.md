# /rival-research

与えられた ASIN と**ほぼ同一の商品**を Amazon の3経路から探し、順位とともにその ASIN 行の直下へ追加する。

3経路すべてブラウザ（claude-in-chrome）で読む。**API では取れない/意味が変わる**ため（後述）。
1 ASIN あたり 9〜12手、5分ほどかかる。**複数 ASIN を渡されたら件数を先にユーザーへ伝える。**

## 何を「ほぼ同一」とするか

**同じ製品・ほぼ同じ仕様のものだけ拾う。** 同じ売り場に並ぶだけの商品は入れない。
判定材料は商品名（素材・形状・設置方法・入数）。迷ったら**入れない**。

例（自社 = `歯ブラシスタンド ステンレス製 置き型 多機能`）

| 候補 | 判定 | 理由 |
|---|---|---|
| Luxspire 歯ブラシスタンド ステンレス製 置き型 | ○ | 素材・設置方法とも一致 |
| レック ステンレス 歯ブラシスタンド 置き型 | ○ | 同上 |
| 無印良品 白磁歯ブラシスタンド 1本用 | × | 素材が違う（磁器） |
| 山崎実業 フィルムフック 歯ブラシホルダー | × | 設置方法が違う（壁掛け） |
| IRETION 歯ブラシスタンド 珪藻土 | × | 素材が違う |
| マーナ 歯ブラシホルダー 吸盤付き 2個入 | × | 設置方法・入数が違う |

**カテゴリが同じでも素材・形状が違えば別物。** 上の例では検索1位・4位・6〜9位がすべて脱落し、
採用できたのは 2位・3位・10位だった。**上位から順に3件ではなく、同一と判定できたものを上から3件。**

## 手順

### 1. 対象行と検索ワードを調べる

```bash
.venv/bin/python rival_research.py target <ASIN>
```

`sheet` / `row_number` / `title` / `keyword` が返る。行が無ければ ASIN をシートへ追加してから。

**`keyword` はシート J列『検索ワード』の1行目**（Ads API の推奨キーワード上位）。
空なら `/market-research` の `fill_keywords.py` を先に流す。手で決めた語を使ってはいけない
（毎回違う語で検索すると順位が比較できなくなる）。

### 2. 3経路をブラウザで読む

`scripts/extract_rivals.js` の中身を `javascript_tool` で実行する。**先頭の `MODE` を経路ごとに書き換える。**

| # | 経路 | 開く URL | MODE |
|---|---|---|---|
| 1 | 関連商品 | `https://www.amazon.co.jp/dp/<ASIN>` | `related` |
| 2 | 検索結果 | `https://www.amazon.co.jp/s?k=<keywordをURLエンコード>` | `search` |
| 3 | ランキング | 1 のページから取る（下記） | `ranking` |

**ランキングの URL は商品ページから取る。** カテゴリIDを推測してはいけない。

```js
// 商品ページで実行。pd_zg_hrsr_ が最も細かいカテゴリのランキング
(() => {
  const a = document.querySelector('a[href*="/gp/bestsellers/"][href*="pd_zg_hrsr"]');
  return a ? a.getAttribute('href').split('/ref=')[0] : 'none';
})()
```

`/gp/bestsellers/kitchen/2574218051` のような相対パスが返るので `https://www.amazon.co.jp` を付けて開く。

各ページとも **navigate → wait 5秒 → 抽出** の順。`browser_batch` で wait と抽出をまとめる。
**navigate は単体で呼ぶ**（batch に混ぜると `Navigation to this domain is not allowed` になることがある）。

### 3. ほぼ同一のものだけ選んで JSON にする

経路ごとに、上から見て同一と判定できたものを**最大3件**。**順位は画面上の実際の順位を入れる**
（同一でないものを飛ばしても番号を詰めない。`関連4` は関連枠の4番目という意味）。

```json
{
  "関連":     [{"asin": "B0F1N7BCGY", "title": "...", "rank": 1}],
  "検索":     [{"asin": "B001FCMOHY", "title": "...", "rank": 3}],
  "ランキング": [{"asin": "B005N5PRO6", "title": "...", "rank": 9}]
}
```

### 4. 書き込む

```bash
.venv/bin/python rival_research.py write <ASIN> --candidates <JSONファイル> --dry-run
.venv/bin/python rival_research.py write <ASIN> --candidates <JSONファイル>
```

- 対象行の**直下**へ候補の数だけ行を挿入し、ASIN列と順位列に書く
- **同じ ASIN が複数経路に出たら1行にまとめる**（`関連1 / 検索2 / ランキング4` を改行区切りで順位列へ）
- 並び順は経路順（関連→検索→ランキング）、経路内は順位順
- 自社 ASIN は候補から自動で外れる（検索結果やランキングには自社も出るため）
- `--limit` で経路ごとの採用件数を変えられる（既定 3）

### 5. 商品情報と数式を埋める

```bash
.venv/bin/python fetch_products.py --sheet "<シート名>" --limit <候補数>
.venv/bin/python fill_formulas.py --sheet "<シート名>"
```

**`fetch_products` は1回で `--limit` 件までしか処理しない。** 埋まらない行が残ったらもう一度流す
（挿入直後は行数の把握が古く、初回で全部埋まらないことがある。実際 6行のうち3行が残った）。

`fill_formulas.py` は**月間販売高・利益・利益率**の数式を、同じ列の既存行からコピーして相対参照だけずらす。
挿入した行には数式が入らないので必ず流す。

## 順位列は E列の次（F列）

列コード `RIVAL_RANK`、見出し『順位』。**`write` が対象タブに無ければ自動で挿入する**ので、
手で足さなくてよい。挿入済みのタブでは何もしない（冪等）。

**列インデックスを固定してはいけない。** 順位列を足したことで、それより右の列がすべて1つずれた
（月間販売高 G→H、利益 AB→AC）。列コードか見出し名で引くこと。

## API では代わりにならない

| 経路 | API | 使えない理由 |
|---|---|---|
| 関連商品 | — | 商品ページの推薦枠は SP-API にも Keepa にも無い |
| 検索結果 | SP-API `searchCatalogItems` | **カタログ検索順であって購買者向け検索順ではない**。買い物客が見る並びと一致しない |
| ランキング | Keepa `/bestsellers` | 集計時点がずれる。トークンも要る |

## セレクタ（2026-09-05 時点で確認済み）

| 経路 | 起点 | 順位の取り方 |
|---|---|---|
| 関連商品 | `#sims-simsContainer_feature_div_0` | `[data-asin]` の出現順 |
| 検索結果 | `div[data-component-type="s-search-result"][data-asin]` | スポンサー枠を除いた通し番号 |
| ランキング | `[id^="gridItemRoot"]` | `.zg-bdg-text` の `#N` |

- **関連商品はスポンサー枠と ID が別。** 広告枠は `#desktop-dp-sims_SponsoredProductsSimsDpDesktop` で、
  見出しは同じ「この商品に関連する商品」。`#sims-simsContainer_feature_div_0` だけを見れば広告は混ざらない
- **検索結果はスポンサー枠を除いてから数える。** 除かないと順位が実際より下にずれる
  （「歯ブラシ置き」では上位4枠が広告だった）
- ランキングは1ページ30件。31位以降が要るときは `?pg=2`
- **抽出スクリプトの戻り値に URL を入れてはいけない**（`[BLOCKED: Cookie/query string data]` でブロックされる）

## 自社の順位も報告する

検索結果とランキングには自社 ASIN も出る。候補行としては書かないが、**会話では必ず伝える**
（例「検索5位・ランキング7位」）。ライバルとの相対位置がこの調査の主眼のため。
