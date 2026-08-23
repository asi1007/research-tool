# research-tool

OEMリサーチシートのC列（ASIN / Amazon商品URL）から、Keepa・SP-APIで商品情報を取得してシートへ書き戻すツール。

## セットアップ

```bash
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env        # KEEPA_API_KEY, SP_API_* を記入
cp <どこかの>service_account.json .
```

## 使い方

```bash
.venv/bin/python fetch_products.py --all --count-only   # 対象行数を数える（APIを呼ばない）
.venv/bin/python fetch_products.py --all --dry-run      # 書き込まずに確認
.venv/bin/python fetch_products.py --all                # 実行
```

既定は**空欄のみ補完**。既存の値は壊さない。全項目を入れ直すときは `--overwrite`。

## テスト

```bash
.venv/bin/python -m pytest src/tests -q
```

## 構成

```
fetch_products.py            CLI
src/domain/                  Asin, ProductInfo, ProductSize
src/usecases/                取得の統合・行更新の計画・一括処理
src/infrastructure/          Keepa, SP-API, gspread, 列マッピング, 送料計算, ログ
src/tests/                   pytest
```

詳細と注意点は `CLAUDE.md` を参照。
