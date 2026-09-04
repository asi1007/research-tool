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

月間販売数（Keepa の `monthlySold`）は **AB列 `販売数/FBA数` と J列 `数量` の両方**へ書く。
J列は本来 I列「金額」の隣にある1688の仕入ロット数の欄だが、2026-08-29 にユーザー方針が変わり
両方へ書くことになった。**J列の既存値（手入力の仕入ロット数）は Python・GAS 両方の経路で保護される**が、
仕組みは経路ごとに異なる。

- Python (`fetch_products.py`): `RowUpdatePlanner` が `needs_fetch` / `_is_blank` で
  書き込み対象列すべての空欄判定を行う。`--overwrite` を付けない限り、既存値がある列は
  J列に限らずどれも上書きしない
- GAS (`fetchAndWriteToSheet`): 他の列（商品名・価格等）は再取得のたびに最新値で
  無条件に上書きするのが元々の仕様。**J列だけ** `SheetDataReader.gs` の
  `updateRowByNumber` が `PROTECTED_EXISTING_VALUE_HEADERS`（`'数量'` のみ）と
  `isBlankCellValue` で個別に保護する。空とみなすのは `null`/`undefined`/空文字/空白のみで、
  既存セルが `0` のときは「値がある」として保護する（新しく書く値が0の場合は書ける）

経緯（AB列のヘッダー正規化）: 2026-08-22 に「正規化は入れない」と判断したが、
その結果 monthlySold がどの列にも入らなくなったため 2026-08-25 に方針を戻した。

経緯（J列への書き込み可否）: 2026-08-24 に一度 J列へも書く実装を入れたが、
手入力値を壊す懸念からいったん外し AB列のみに絞った。2026-08-29 に方針変更で
両方へ書く形に戻し、GAS側にはJ列専用の既存値保護（上記）を追加した。

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

## 売れ筋新商品の発見（Keepa Product Finder）

`discover_products.py` が条件に合う ASIN を自動調査タブへ積む。手順は `/market-research`。

- **価格帯はタブ名から読む。** `自動調査1000円以下` → 1〜1000円、`自動調査1000円-2000円` → **1001**〜2000円、
  `自動調査3000円以上` → 3001円〜。**タブを足すだけで新しい価格帯を回せる**（コードは触らない）。
  `A円-B円` の下限を `A+1` にしてあるので隣の帯と重ならない。読み取れないタブ名は実行せず exit 1
- 定期実行は `--all-sheets`。価格の安い順に全帯を処理し、**前の帯で積んだ ASIN は次の帯へ積まない**
- **化粧品はルートカテゴリ「ビューティー」(`52374051`) ごと除外。** 薬機法で輸入できないため。
  ルートで落としているのでメイクブラシ等の雑貨も巻き添えになる
- **抽出は「販売数 × 価格が月商50万円以上」。** Keepa は積で絞れないので、帯の上限価格で
  必要な最低販売数を出して足切りし、未知ASINだけ実測（`/product`）して絞る
- **除外カテゴリでもすり抜ける商品がある。** `categories_exclude` は `categoryTree` を見るため、
  ツリーが空の商品は弾けない（2026-09-03 に食品が1件通った）。実測の `rootCategory` で再度ふるう
- **ポケモンカードはサブカテゴリで除外する。** トレカは「ホビー」配下にあり、ルートごと落とすと
  プラモ・鉄道模型まで消える（`2189358051` / `10345415051`）
- **A列の `d` は消すだけでは足りない。** `drop_marked.py` で**候補外タブへ移してから**削除する。
  行を消しただけだと既知ASINから外れ、翌朝の定期実行でまた積まれる
- **検索ワード(M)と広告単価(Y)は Amazon Ads API の推奨キーワードから入れる。** 資格情報は
  `data-engineer/dwld-ad-data/.env` を `AD_CREDENTIALS_ENV` 経由で借りる。**`bid` は円の1/100**（9700→97円）。
  **N列『検索数』は公式APIに存在しない**（セラースプライトの手入力のまま）
- **検索順位(BT)は Brand Analytics の検索キーワードレポートから取る。** `searchFrequencyRank` は
  検索数ではなく順位。**`dataStartTime` が日曜でないと FATAL**。43万語超・数十MBあるので週単位でキャッシュする
- **`releaseDate` は 0 の商品が大半で使えない。** 発売日の判定は `listedSince`（Amazon 出品日）
- **Amazon 本体の除外は `availabilityAmazon: [-1]`。** `current_AMAZON` の範囲指定は 0件になる
- **`perPage` は 50 未満だと 400 エラー。** 1回 11トークン

### 書き込み先の行と列は、書く直前に自分で決める
**`fetch_products` も同じ事故を起こした（2026-09-05）。** 取得に時間がかかる間に
`rival_research.py write` が行を挿入し、読み取り時の行番号で書いたため **8行が1行ずれた**。
自社行の商品名が競合の商品名で上書きされ、SP-API で全行を突合するまで気づけなかった。
`BulkFetchProductsUseCase._flush` が書き込み直前に ASIN で引き直すようにした（`row_relocator.py`）。

**同じシートに対する書き込みを並行実行しない。** このときは `fetch_products` を
バックグラウンドで複数起動しており、それぞれが古い行番号を持っていた。Keepa の
トークン待ちで待機している間も行番号は古くなり続ける。


**読み取り時の行番号を書き込みに使ってはいけない。** 読み取りから書き込みまでの間に
行が挿入・削除されると全件ずれる。2026-08-31 に `shorten_titles` の短縮名 52件が1行ずれた
（`claude -p` の待ち時間にシートの行が動いた）。書き込む直前に **ASIN で行を引き直す**
（`relocate_batch`。ASIN が無い手入力タブは商品名で引く）。

**gspread の `append_rows` に表の左端を判定させてはいけない。** 候補外タブで **DE列（108列目）から**
書かれた。行番号と列位置を自分で決めて `apply_updates` で書く（`plan_append_rows`）。

## ライバル商品調査

`/rival-research` が ASIN と**ほぼ同一の商品**を3経路（商品ページの関連商品・検索結果・カテゴリランキング）から
探し、順位とともにその ASIN 行の直下へ追加する。手順と判定基準は `.claude/commands/rival-research.md`。

- **順位列（F列 `RIVAL_RANK`）を足したので、それより右の列が1つずれた**（月間販売高 G→H、利益 AB→AC）。
  列インデックスを固定しているコードがあれば壊れる。列コードか見出し名で引くこと
- **3経路とも playwright で読む**（`rival_research.py collect`）。SP-API の `searchCatalogItems` は
  カタログ検索順であって買い物客が見る検索結果の並びではなく、関連商品の枠は API に存在しない
- **Amazon は素の Chromium に「ショッピングを続ける」の中間ページを返す。** ボタンを押すとトップへ
  飛ばされるので通過後に目的 URL を開き直し、プロファイル（`ms-playwright/research-amazon`）を残して
  次回以降は出ないようにしてある。0件が返ったら `--headed` で実際の表示を見る
- **同じ ASIN が複数経路に出たら1行にまとめる**（順位列へ `関連1 / 検索2 / ランキング4` を改行区切り）
- 挿入した行には数式が入らないので `fill_formulas.py` で月間販売高・利益・利益率を補う
- **有名ブランドは候補にしない。** `EXCLUDED_BRANDS` を市場調査と共用しており、レック・ダルトン・
  山崎実業・無印良品・マーナ等は同じ棚に並んでも中国輸入の競合にならないため弾く。
  ブランドを足したら `rival_research.py prune` で既存のライバル行も消す

## テスト

GAS には実行環境が無いので、テスト関数を `.gs` に同梱して両方から実行できるようにしている。

```bash
# ローカル（Node）
{ echo 'const Logger = { log: console.log };'; cat Asin.gs; echo 'testAsinParse();'; } > /tmp/t.js && node /tmp/t.js

# Apps Script エディタ
testAsinParse() / testKeepaMainImage() / testFindTemplateRowOffset() / testNormalizeHeader() / testIsBlankCellValue()
```

`SpreadsheetApp` に依存する部分はモックできないため、判定ロジックを純粋関数に切り出してテストする
（`findTemplateRowOffset` や、J列の既存値保護に使う `isBlankCellValue`（`SheetDataReader.gs`）がその例）。

## デプロイ

```bash
clasp push
```

**`.claspignore` を消さないこと。** 無いと `.venv` 配下の `.js`（urllib3 の
`emscripten_fetch_worker.js`）まで GAS プロジェクトへ push される。実際に混入させた。
