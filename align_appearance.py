from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.sheet_appearance import HEADER_ROWS, build_requests

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_REFERENCE_SHEET = "自動調査1000円-2000円"
DEFAULT_TEMPLATE_ROWS = 10

logger = logging.getLogger("align_appearance")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="タブの列幅・非表示列・固定行・行の高さ・表示形式を、見本のタブに揃える"
    )
    parser.add_argument("sheet", help="揃える対象のタブ")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE_SHEET, help="見本にするタブ")
    parser.add_argument(
        "--template-rows",
        type=int,
        default=DEFAULT_TEMPLATE_ROWS,
        help="見本のタブで表示形式を読み取るデータ行数（最頻の書式を採る）",
    )
    parser.add_argument("--dry-run", action="store_true", help="送らずにリクエストだけ表示する")
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args()


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    repository = build_repository()
    target = repository.spreadsheet.worksheet(args.sheet)
    appearance = repository.read_appearance(args.reference, args.template_rows)
    requests = build_requests(appearance, target.id, target.row_count, HEADER_ROWS)

    if args.dry_run:
        print(json.dumps(requests, ensure_ascii=False, indent=2))
        return

    repository.apply_requests(requests)
    logger.info(
        "見た目を揃えました",
        extra={
            "context": {
                "sheet": args.sheet,
                "reference": args.reference,
                "requests": len(requests),
            }
        },
    )


if __name__ == "__main__":
    main()
