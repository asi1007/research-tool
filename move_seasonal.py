from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_band import discovery_sheets
from src.domain.value_objects.seasonal_verdicts import SeasonalVerdicts
from src.infrastructure.claude_cli import ClaudeCli, ClaudeCliError
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.seasonal_verdict_store import JsonSeasonalVerdictStore
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.drop_marked import plan_transfer
from src.usecases.seasonal import (
    SEASONAL_SHEET,
    SeasonalCandidate,
    build_judge_prompt,
    parse_judge_response,
    rows_to_move,
    seasonal_candidates,
)
from src.usecases.shorten_titles import DEFAULT_BATCH_SIZE

PROJECT_ROOT = Path(__file__).resolve().parent
VERDICTS_PATH = PROJECT_ROOT / "data" / "seasonal_verdicts.json"

logger = logging.getLogger("move_seasonal")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"夏物・冬物の行を「{SEASONAL_SHEET}」タブへ移し、元タブから削除する"
    )
    parser.add_argument("--sheet", help="対象タブ（省略時はすべての自動調査タブ）")
    parser.add_argument("--dry-run", action="store_true", help="移さず対象だけ表示する")
    parser.add_argument(
        "--not-seasonal",
        nargs="+",
        default=[],
        metavar="ASIN",
        help="人が季節商品ではないと判断したASINを記録する（以後は移さない）。シートは触らない",
    )
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args(argv)


def build_repository() -> GoogleSheetRepository:
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def resolve_sheets(args: argparse.Namespace, repository: GoogleSheetRepository) -> list[str]:
    if args.sheet:
        return [args.sheet]
    return discovery_sheets(repository.sheet_titles())


def run(
    args: argparse.Namespace,
    repository: GoogleSheetRepository | None = None,
    cli: ClaudeCli | None = None,
    store: JsonSeasonalVerdictStore | None = None,
) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    store = store or JsonSeasonalVerdictStore(VERDICTS_PATH)

    if args.not_seasonal:
        return record_not_seasonal(args.not_seasonal, store)

    repository = repository or build_repository()
    cli = cli or ClaudeCli()
    verdicts = store.load()
    total = 0
    exit_code = 0

    for sheet in resolve_sheets(args, repository):
        values = repository.read_values(sheet)
        candidates = seasonal_candidates(values)
        judged = judge_candidates(candidates, verdicts, cli)
        exit_code = exit_code or (0 if judged else 1)
        if not args.dry_run:
            store.save(verdicts)
        total += move_rows(args, sheet, values, rows_to_move(candidates, verdicts), repository)

    logger.info("完了しました", extra={"context": {"moved": total}})
    return exit_code


def record_not_seasonal(raw_asins: list[str], store: JsonSeasonalVerdictStore) -> int:
    asins = [Asin.parse(raw) for raw in raw_asins]
    if any(asin is None for asin in asins):
        logger.error("ASINを読み取れません", extra={"context": {"asins": raw_asins}})
        return 1

    verdicts = store.load()
    for asin in asins:
        verdicts.record_human(str(asin), False)
    store.save(verdicts)
    logger.info("季節商品ではないと記録しました", extra={"context": {"asins": [str(a) for a in asins]}})
    return 0


def judge_candidates(
    candidates: list[SeasonalCandidate], verdicts: SeasonalVerdicts, cli: ClaudeCli
) -> bool:
    unjudged = set(verdicts.unjudged([candidate.asin for candidate in candidates]))
    pending = list({c.asin: c for c in candidates if c.asin in unjudged}.values())
    succeeded = True

    for start in range(0, len(pending), DEFAULT_BATCH_SIZE):
        batch = pending[start : start + DEFAULT_BATCH_SIZE]
        # 判定できなかった行は移さない。誤って移すと元タブから消えて気づけない
        try:
            result = parse_judge_response(cli.complete(build_judge_prompt([c.title for c in batch])), len(batch))
        except ClaudeCliError as error:
            logger.error("季節商品の判定に失敗しました", extra={"context": {"size": len(batch), "error": str(error)}})
            succeeded = False
            continue
        if result.error is not None:
            logger.error("季節商品の判定を解析できません", extra={"context": {"size": len(batch), "error": result.error}})
            succeeded = False
            continue
        for index, seasonal in result.verdicts.items():
            verdicts.record_claude(batch[index].asin, seasonal)

    return succeeded


def move_rows(
    args: argparse.Namespace,
    sheet: str,
    values: list[list],
    row_numbers: list[int],
    repository: GoogleSheetRepository,
) -> int:
    if not row_numbers:
        return 0

    for candidate in seasonal_candidates(values):
        if candidate.row_number in row_numbers:
            print(f"{sheet}\t{candidate.row_number}\t{candidate.asin}\t{candidate.title[:34]}")

    if args.dry_run:
        return len(row_numbers)

    plan = plan_transfer(values, repository.read_values(SEASONAL_SHEET), row_numbers)
    repository.ensure_rows(SEASONAL_SHEET, max(plan))
    repository.apply_updates(SEASONAL_SHEET, plan)
    repository.delete_rows(sheet, row_numbers)

    logger.info(
        f"{SEASONAL_SHEET}へ移しました",
        extra={"context": {"sheet": sheet, "rows": len(row_numbers)}},
    )
    return len(row_numbers)


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
