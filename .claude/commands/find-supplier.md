# /find-supplier

リサーチシートの商品画像から 1688 の同款を画像検索し、上位3件を仕入先候補として登録する。

## 前提

1688 はヘッドレスでは開けない（`验证码拦截` で遮断される）。
**必ず claude-in-chrome（ユーザーのログイン済み Chrome）を使う。**

## Step 1: 対象行を出す

```bash
.venv/bin/python find_supplier.py targets --sheet "<シート名>" --limit 10
```

購入先が空で画像がある行だけが返る。0件なら終了する。各行には `title`（Amazon商品名。`TITLE_SELL` 列）も含まれる。

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
9. **各候補の数量倍率を判定する。** 1688 は個数単価で表示されることが多く（例: 磁石1個 ¥0.03）、
   Amazon側はセット単位で売られている（例: 磁石50個入り）。このズレを埋めないと価格計算が
   実際の何十分の一にもなる。

   Step 1 の `targets` 出力の `title`（Amazon商品名）と、Step 2-7 で取れた各候補の `title`
   （1688の中国語タイトル。「1件起批」等の単位表記を含むことがある）を読み、
   1688の1件（1個）が Amazonの1リスティングに対して何個分に当たるかを候補ごとに判断する。

   例: Amazon側が「マグネット 50個セット」、1688側が「钕铁硼磁铁…1件起批」（1個から購入可、
   価格は1個あたり）なら、その候補の `quantity` は `50`。候補によって単位（1個売り／100個セット
   売り等）が異なることがあるため、**3件それぞれについて個別に判断する。**

   判断できない場合は `quantity` を `1` にする（推測で埋めない）。

   判定したら、抽出した JSON の各候補オブジェクトへ `quantity` フィールド（正の整数）を追加してから
   保存する。
10. 書き戻す

   ```bash
   .venv/bin/python find_supplier.py write --sheet "<シート名>" --row <行番号> --candidates <JSONファイル>
   ```

## 注意

- **`imageAddress` パラメータで画像URLを渡してはいけない。** 画像は表示されるが検索結果が0件になる
- **キャプチャが出たら停止する。** ユーザーに手動での通過を依頼し、以降の行は処理しない
- 検索結果が0件だった行は何も書かず、ASIN をログに残して次へ進む
- 開いたタブは `mcp__claude-in-chrome__tabs_close_mcp` で閉じる
