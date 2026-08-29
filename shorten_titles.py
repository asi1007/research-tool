from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.claude_cli import ClaudeCli, ClaudeCliError
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.shorten_titles import (
    DEFAULT_BATCH_SIZE,
    build_prompt,
    build_updates,
    chunk_targets,
    extract_targets,
    parse_batch_response,
)

PROJECT_ROOT = Path(__file__).resolve().parent

logger = logging.getLogger("shorten_titles")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="商品名(TITLE_SELL)からH列『商品名(BUY)』へ10文字以内の短縮名を入れる"
    )
    parser.add_argument("--limit", type=int, help="処理する行数の上限")
    parser.add_argument("--dry-run", action="store_true", help="書き込まず対象件数と短縮名の対応を表示する")
    parser.add_argument("--sheet", help="対象タブを絞る(省略時は全タブ)")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def run(
    args: argparse.Namespace,
    repository: GoogleSheetRepository | None = None,
    cli: ClaudeCli | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    repository = repository or build_repository()
    cli = cli or ClaudeCli()

    sheet_values = repository.read_all_values()
    if args.sheet:
        if args.sheet not in sheet_values:
            logger.error("指定されたタブが見つかりません", extra={"context": {"sheet": args.sheet}})
            return 1
        sheet_values = {args.sheet: sheet_values[args.sheet]}

    targets = extract_targets(sheet_values)
    if args.limit is not None:
        targets = targets[: args.limit]

    logger.info("対象行を抽出しました", extra={"context": {"count": len(targets)}})

    if not targets:
        return 0

    # バッチごとに解析後ただちに書き込む。全バッチ完走後にまとめて書くと、
    # 途中のバッチで例外が起きたとき、既に生成済みの短縮名まで失われるため。
    batches = chunk_targets(targets, batch_size)
    skipped_batches = 0
    total_written = 0

    for batch_index, batch in enumerate(batches):
        prompt = build_prompt([target.title for target in batch])

        try:
            response_text = cli.complete(prompt)
        except ClaudeCliError as error:
            logger.error(
                "claude -p の呼び出しに失敗したためこのバッチをスキップします",
                extra={"context": {"batch": batch_index, "size": len(batch), "error": str(error)}},
            )
            skipped_batches += 1
            continue

        result = parse_batch_response(response_text, len(batch))
        if result.error is not None:
            logger.error(
                "応答の検証に失敗したためこのバッチをスキップします",
                extra={"context": {"batch": batch_index, "size": len(batch), "error": result.error}},
            )
            skipped_batches += 1
            continue

        if args.dry_run:
            for index, target in enumerate(batch):
                print(f"{target.sheet}\t{target.row_number}\t{target.title}\t→\t{result.short_titles[index]}")
            continue

        batch_updates = build_updates(batch, result.short_titles)
        for sheet_name, row_updates in batch_updates.items():
            written = repository.apply_updates(sheet_name, row_updates)
            total_written += written
            logger.info(
                "書き込みました",
                extra={"context": {"sheet": sheet_name, "batch": batch_index, "cells": written}},
            )

    logger.info(
        "完了しました",
        extra={
            "context": {
                "batches": len(batches),
                "skipped_batches": skipped_batches,
                "cells": total_written,
            }
        },
    )
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
