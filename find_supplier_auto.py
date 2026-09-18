from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.discovery_band import discovery_sheets
from src.domain.value_objects.supplier_skips import SupplierSkips
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository, SheetTable
from src.infrastructure.alibaba_scraper import DEFAULT_VARIANT_OFFERS, CaptchaError, collect
from src.usecases.build_supplier_updates import build_updates
from src.usecases.find_supplier_auto import (
    DEFAULT_BATCH,
    EMPTY_CANDIDATES_REASON,
    build_decision_prompt,
    looks_blocked,
    parse_decision,
    pick_batch,
    skip_reason_for,
)
from src.infrastructure.candidate_parser import parse_candidates
from src.usecases.select_supplier_targets import select_targets

PROJECT_ROOT = Path(__file__).resolve().parent
SKIPS_PATH = PROJECT_ROOT / "data" / "supplier_skips.json"
IMAGE_DIR = PROJECT_ROOT / "data" / "supplier_images"
CLAUDE_BIN = Path("/opt/homebrew/bin/claude")
# 1商品あたり5〜8手。5件で20分前後かかる
DEFAULT_TIMEOUT_SECONDS = 2400
EXIT_CAPTCHA = 2
EXIT_BLOCKED = 3

logger = logging.getLogger("find_supplier_auto")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="仕入先が未記入の行を playwright で 1688 から集め、どの候補・規格かだけ claude -p に選ばせて書き込む"
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_BATCH, help=f"1回に処理する件数（既定 {DEFAULT_BATCH}）")
    parser.add_argument("--sheet", help="対象タブを1つに絞る（省略時は価格の安い自動調査タブから）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="claude の実行上限（秒）")
    parser.add_argument(
        "--variant-offers",
        type=int,
        default=DEFAULT_VARIANT_OFFERS,
        help=f"規格表まで開く候補の数（既定 {DEFAULT_VARIANT_OFFERS}）",
    )
    parser.add_argument("--dry-run", action="store_true", help="claude を起動せず、渡すプロンプトだけ表示する")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args(argv)


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def collect_targets(args: argparse.Namespace, repository: GoogleSheetRepository) -> dict[str, list]:
    sheets = [args.sheet] if args.sheet else discovery_sheets(repository.sheet_titles())
    collected: dict[str, list] = {}
    for sheet in sheets:
        values = repository.read_values(sheet)
        collected[sheet] = select_targets(SheetTable(values), ColumnCodes(values), limit=args.limit * 4)
    return collected


def download_image(target, directory: Path) -> Path:
    import urllib.request

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{target.asin}.jpg"
    if not path.exists():
        with urllib.request.urlopen(target.image_url, timeout=60) as response:
            path.write_bytes(response.read())
    return path


def write_candidates(sheet: str, target, decided: list[dict], repository: GoogleSheetRepository) -> int:
    """書き込む直前に ASIN で行を引き直す。取得の間に行が動いていることがある。"""
    values = repository.read_values(sheet)
    codes = ColumnCodes(values)
    asin_index = codes.index_of("ASIN_SELL")
    rows = [
        number
        for number, row in enumerate(values, 1)
        if number > 3 and asin_index < len(row) and target.asin in str(row[asin_index])
    ]
    if len(rows) != 1:
        logger.warning("行を特定できません", extra={"context": {"asin": target.asin, "rows": rows}})
        return 0
    updates = build_updates(rows[0], parse_candidates(decided), codes)
    return repository.apply_updates(sheet, {rows[0]: updates})


def run_claude(prompt: str, timeout: int) -> tuple[int, str]:
    command = [str(CLAUDE_BIN), "--print", "--dangerously-skip-permissions", prompt]
    try:
        completed = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return 1, f"claude がタイムアウトしました（{timeout}秒）"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def run(args: argparse.Namespace, repository: GoogleSheetRepository | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    repository = repository or build_repository()
    skips = SupplierSkips.load(SKIPS_PATH)

    sheet, batch = pick_batch(collect_targets(args, repository), skips, limit=args.limit)
    if sheet is None:
        logger.info("仕入先が未記入の行はありません")
        return 0

    logger.info(
        "調べます",
        extra={"context": {"sheet": sheet, "asins": [target.asin for target in batch]}},
    )

    written_rows = 0
    empty_asins: list[str] = []
    found_count = 0
    for target in batch:
        try:
            scraped = collect(download_image(target, IMAGE_DIR), variant_offers=args.variant_offers)
        except CaptchaError:
            # キャプチャは人が通すしかない。ここで止めてラッパーから Slack へ流す
            logger.error("CAPTCHA_STOP キャプチャで止まりました", extra={"context": {"asin": target.asin}})
            skips.save(SKIPS_PATH)
            return EXIT_CAPTCHA
        except Exception as error:  # noqa: BLE001 - 1件の失敗で残りを止めない
            logger.error("1688を開けません", extra={"context": {"asin": target.asin, "error": str(error)}})
            continue

        empty_reason = skip_reason_for(scraped)
        if empty_reason is not None:
            # 候補ゼロを claude に投げても飛ばす判断しか返らない。遮断と区別できたら最後にまとめて記録する
            empty_asins.append(target.asin)
            logger.info("候補が出ません", extra={"context": {"asin": target.asin}})
            continue
        found_count += 1

        prompt = build_decision_prompt(target, scraped)
        if args.dry_run:
            print(prompt)
            continue

        code, output = run_claude(prompt, args.timeout)
        decided, skip_reason = parse_decision(output)
        if skip_reason is not None:
            skips.add(target.asin, skip_reason)
            logger.info("飛ばします", extra={"context": {"asin": target.asin, "reason": skip_reason}})
            continue
        written_rows += 1 if write_candidates(sheet, target, decided, repository) else 0

    if looks_blocked(len(empty_asins), found_count):
        logger.error(
            "1688が結果を返しません（遮断の可能性）。飛ばす記録は残しません",
            extra={"context": {"sheet": sheet, "asins": empty_asins}},
        )
        skips.save(SKIPS_PATH)
        return EXIT_BLOCKED

    for asin in empty_asins:
        skips.add(asin, EMPTY_CANDIDATES_REASON)
    skips.save(SKIPS_PATH)
    logger.info(
        "終わりました",
        extra={"context": {"sheet": sheet, "written": written_rows, "skipped": len(empty_asins)}},
    )
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
