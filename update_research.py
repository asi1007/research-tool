from __future__ import annotations

import argparse
import fcntl
import logging
import subprocess
import sys
from pathlib import Path
from typing import IO

from src.infrastructure.logging_config import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parent
DISCOVER_MAX_LOOKUPS = 150
# Keepa の補充レートで1件12秒。1回で溜まりを全部さらうと次の起動までに終わらず、
# ロックに弾かれ続けて後続の工程（数式・仕入先）へ永久に進めない
FETCH_LIMIT_PER_SHEET = 30
# 同じシートへ並行して書き込むと読み取り時の行番号がずれる。入口をこの1本に絞る前提のロック
LOCK_PATH = PROJECT_ROOT / ".update_research.lock"

logger = logging.getLogger("update_research")


def _sheet_option(sheet: str | None) -> list[str]:
    return ["--sheet", sheet] if sheet else []


def drop_command(sheet: str | None) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "drop_marked.py"),
        *_sheet_option(sheet),
    ]


def fetch_command(sheet: str | None) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "fetch_products.py"),
        *(_sheet_option(sheet) or ["--all"]),
        "--interval",
        "auto",
        "--limit",
        str(FETCH_LIMIT_PER_SHEET),
    ]


def formula_command(sheet: str | None) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "fill_formulas.py"),
        *_sheet_option(sheet),
    ]


def supplier_command(sheet: str | None) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "find_supplier_auto.py"),
        *_sheet_option(sheet),
    ]


def discover_command(sheet: str | None) -> list[str]:
    return [
        sys.executable,
        str(PROJECT_ROOT / "discover_products.py"),
        *(_sheet_option(sheet) or ["--all-sheets"]),
        "--max-lookups",
        str(DISCOVER_MAX_LOOKUPS),
    ]


def steps(args: argparse.Namespace) -> list[list[str]]:
    commands = [
        drop_command(args.sheet),
        fetch_command(args.sheet),
        formula_command(args.sheet),
        supplier_command(args.sheet),
    ]
    if args.discover:
        commands.insert(0, discover_command(args.sheet))
    return commands


def run(args: argparse.Namespace) -> int:
    commands = steps(args)
    if args.dry_run:
        for command in commands:
            print(" ".join(command))
        return 0

    exit_code = 0
    for command in commands:
        step = Path(command[1]).name
        logger.info("工程を開始します", extra={"context": {"step": step, "sheet": args.sheet}})
        step_exit_code = subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode
        if step_exit_code:
            logger.error(
                "工程が失敗しました",
                extra={"context": {"step": step, "exit_code": step_exit_code}},
            )
        exit_code = exit_code or step_exit_code
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="リサーチシートの印の移動・商品情報・数式・仕入先を順に更新する"
    )
    parser.add_argument("--sheet", help="対象タブ（省略時は各工程の既定＝自動調査タブすべて）")
    parser.add_argument(
        "--discover", action="store_true", help="先に Keepa で新商品を探して積む"
    )
    parser.add_argument("--dry-run", action="store_true", help="実行せず工程のコマンドだけ出す")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args(argv)


def acquire_lock(path: Path) -> IO[str] | None:
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    if args.dry_run:
        return run(args)

    handle = acquire_lock(LOCK_PATH)
    if handle is None:
        logger.warning(
            "前回の実行が終わっていないので見送りました",
            extra={"context": {"lock": str(LOCK_PATH)}},
        )
        return 0
    try:
        return run(args)
    finally:
        handle.close()


if __name__ == "__main__":
    sys.exit(main())
