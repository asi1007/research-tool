# research-tool

Amazon の ASIN／商品URL からリサーチシートを自動で埋める Google Apps Script プロジェクト。
`clasp` でデプロイする。Python 版（`src/`）は同じロジックの移植で、ローカル実行用。

各クラスの役割は `WARP.md` にある。ここには**知らないと事故る前提**だけを書く。

## リサーチシート

`1rW5T03lej-UhQV738VBYra0nCfdS_oiwrWDHbanRdJY` の各タブ（`リサーチ700円以下` など）が対象。

### ヘッダーは2行目と3行目に分かれている

結合セルのため、列によってヘッダーが 2 行目にあったり 3 行目にあったりする。
`SheetDataReader` は `headerRow = 3` を読み、**空なら 2 行目の値で補う**。

| 例 | ヘッダーの行 |
|---|---|
| F列 `画像URL`、AA列 `カート価格`、AP列 `利益` | 2 行目 |
| K列 `発売日`、AC列 `サイズ（長さ）`、AF列 `重量` | 3 行目 |

**列インデックスを固定してはいけない**（親リポジトリの規約）。必ずヘッダー名で引く。

### ヘッダーには改行と先頭空白が混じっている

見た目では分からない。実データは以下のとおり。

| 列 | 実際のヘッダー文字列 |
|---|---|
| AB | `販売数\n/FBA数`（改行入り） |
| AH | `購入\n価格`（改行入り） |
| AE | `" サイズ(高さ)"`（**先頭にスペース**） |

`ProductInfoFetcher.gs` の `allUpdateData` のキー `' サイズ(高さ)'` に先頭スペースが直書きされているのは
これが理由。消すと書き込まれなくなる。

### ヘッダーは normalizeHeader で空白を全除去してから照合する

**`SheetDataReader` は読み込んだヘッダーに `normalizeHeader()` を掛けて保持する。**
`\s+` を全除去するので、改行入り（`販売数\n/FBA数`）も先頭スペース付き（` サイズ(高さ)`）も
そのまま照合できる。照合（`includes`）と書き込み（`indexOf`）は同じ配列を見るため、
ここで揃えれば両方が一度に直る。

**`allUpdateData` のキーも空白なしで書くこと。** 実ヘッダーに合わせて
` サイズ(高さ)` のように空白を直書きしてはいけない。正規化後は一致しなくなる。

月間販売数（Keepa の `monthlySold`）の行き先は **AB列 `販売数/FBA数` のみ**。
J列 `数量` は I列「金額」の隣にある仕入ロット数の欄なので書かない
（2026-08-24 に一度書き込む実装だったが、手入力値を壊すため外した）。

経緯: 2026-08-22 に「正規化は入れない」と判断したが、その結果 monthlySold が
どの列にも入らなくなったため 2026-08-25 に方針を戻した。

### 利益(AP)・利益率(AQ) は既存行からコピーする

取得した値からは決まらない数式列。**数式を文字列で組み立て直さない。**
`copyTo(SpreadsheetApp.CopyPasteType.PASTE_FORMULA)` を使い、相対参照の調整は Sheets に任せる。

```
AP: =AA4-AH4-AJ4-AK4-AM4-AN4    （カート価格 - 購入価格 - 国際送料 - 関税消費税 - 販売手数料 - FBA手数料）
AQ: =AP4/AA4
```

雛形は `FORMULA_HEADER_NAMES` の列で最初に数式がある行を自動で探す。

## Keepa API

### `imagesCSV` は廃止された。`images` 配列を使う

2026-08-22 に F列の画像が全滅していた原因。**`imagesCSV` は全商品で `null` を返す。**

```json
images: [{"l": "61oQj2FPnjL.jpg", "m": "31ighfPhoIL.jpg", "variant": "MAIN"}, ...]
```

`variant === 'MAIN'` の `l`（大サイズ）を取り、`https://m.media-amazon.com/images/I/{l}` を組み立てる。
`extractMainImageFileName()` は旧 `imagesCSV` にもフォールバックするので、Keepa が戻しても壊れない。

当時 F列が埋まっていた行は、SP-API のフォールバックがたまたま成功した行だけだった。

## ASIN列にはURLが入っている

シートの ASIN 列には素の ASIN と Amazon の商品URLが混在する。`Asin.parse()` が両方を解釈する
（`/dp/` `/gp/product/` `/gp/aw/d/` `/product/`、NFKC 正規化で全角・小文字にも対応）。
`amzn.to` の短縮URLは展開しないので `null` になり、その行はスキップされる。

## 手数料に 0 を書かない

**AM列 `販売手数料` と AN列 `配送代行手数料（FBA手数料）` に 0 を書き込んではいけない。**
Amazon は販売時に必ず販売手数料を取るため 0 は正当な値になりえず、書くと利益が過大に出る。

カート価格が取れない場合と手数料APIが失敗した場合に 0 を書いており、
2026-08-25 に4シート18行（36セル）で発生していた。GAS・Python とも修正済み。

- GAS: 手数料が0なら `null` にし、`null` の列は書き込まずログに残す
- Python: `ZERO_WRITABLE_FIELDS` から `referral_fee` / `fba_fee` を除外

**カート価格・販売数・国際送料の 0 はそのまま書く。** これらは「本当に0」がありえるうえ、
空欄だと未取得と区別できず毎回再取得されるため。手数料だけを例外にしている。

## 仕入先探し（1688）

**AiPrice（旧 AliPrice）に公開APIは無い**（2026-08-22 確認）。
旧 `api.aliprice.com` は `https://www.aiprice.com/` へ 302 リダイレクトされ、ドキュメントは消滅。
提供形態はブラウザ拡張のみで、サーバーからは叩けない。

画像検索による自動登録は `/find-supplier`。手順と落とし穴は
`.claude/commands/find-supplier.md` に集約してある。特に次の3点は知らないと必ず詰まる。

- **「搜索图片」は `div.search-btn`。** ref クリックも座標クリックも空振りするので、
  JS で `pointerdown`→`click` のイベント列を送る。成功すると URL に `imageId=` が付く
- **カードの価格は最安サイズのもの。** サイズ違いで単価が数倍変わるため、
  商品ページのサイズ表（`scripts/extract_variants.js`）から対応サイズを選ぶ
- **平面で無地の商品は当たらない。** ステンレス板・マグネットシートは
  花の包装紙や色画用紙が返る。候補が別カテゴリなら書かずに次へ進む

1688 URL が決まったあとの仕入先登録は、親リポジトリのスキル `register-supplier` で自動化済み。

## テスト

GAS には実行環境が無いので、テスト関数を `.gs` に同梱して両方から実行できるようにしている。

```bash
# ローカル（Node）
{ echo 'const Logger = { log: console.log };'; cat Asin.gs; echo 'testAsinParse();'; } > /tmp/t.js && node /tmp/t.js

# Apps Script エディタ
testAsinParse() / testKeepaMainImage() / testFindTemplateRowOffset()
```

`SpreadsheetApp` に依存する部分はモックできないため、判定ロジックを純粋関数に切り出してテストする
（`findTemplateRowOffset` がその例）。

## デプロイ

```bash
clasp push
```

**`.claspignore` を消さないこと。** 無いと `.venv` 配下の `.js`（urllib3 の
`emscripten_fetch_worker.js`）まで GAS プロジェクトへ push される。実際に混入させた。
