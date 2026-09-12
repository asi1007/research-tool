from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import DEFAULT_HEADER_ROW, GoogleSheetRepository
from src.usecases.move_rows import MoveDestination, MovePlan, build_move_plan

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ASIN で行を別タブへ移す（列コードで対応させ、数式は移動先へ書き換える）")
    parser.add_argument("asins", nargs="+", help="移す ASIN")
    parser.add_argument("--to", required=True, help="移動先タブ名")
    parser.add_argument("--from", dest="source", help="移動元タブ名（省略時は全タブから探す）")
    parser.add_argument("--at", choices=[d.value for d in MoveDestination], default=MoveDestination.TOP.value,
                        help="挿入位置。top はヘッダー直下、bottom は末尾（既定: top）")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def find_source_sheet(repository: GoogleSheetRepository, dest: str, asins: list[str]) -> str | None:
    wanted = {a.upper() for a in asins}
    for sheet, values in repository.read_all_values().items():
        if sheet == dest or not values:
            continue
        codes = ColumnCodes(values)
        asin_column = codes.index_of("ASIN_SELL")
        if asin_column is None:
            continue
        from src.domain.value_objects.asin import Asin

        for row in values[DEFAULT_HEADER_ROW:]:
            cell = str(row[asin_column]) if asin_column < len(row) else ""
            parsed = Asin.parse(cell)
            if parsed and parsed.value in wanted:
                return sheet
    return None


def describe(plan: MovePlan, source: str, dest: str) -> str:
    last = plan.insert_at + plan.row_count - 1
    return f"{source} → {dest} 行{plan.insert_at}〜{last} へ {plan.row_count}行"


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    repository = GoogleSheetRepository(
        str(ROOT / require_env("SERVICE_ACCOUNT_FILE")), require_env("RESEARCH_SPREADSHEET_ID")
    )

    source = args.source or find_source_sheet(repository, args.to, args.asins)
    if source is None:
        logger.error("移動元が見つかりません", extra={"context": {"asins": args.asins}})
        return 1
    if source == args.to:
        # 同じタブ内で挿入と削除を続けると、削除する行番号が挿入分ずれて別の行を消す
        logger.error("同じタブ内では移せません", extra={"context": {"sheet": source}})
        return 1

    source_values = repository.read_values(source)
    dest_values = repository.read_values(args.to)
    plan = build_move_plan(
        source_values, dest_values, args.asins, MoveDestination(args.at), DEFAULT_HEADER_ROW
    )

    if plan.missing_asins:
        logger.warning("見つからない ASIN があります", extra={"context": {"asins": plan.missing_asins}})
    if plan.dropped_codes:
        logger.warning("移動先に無い列は落とします", extra={"context": {"codes": plan.dropped_codes}})
    if not plan.updates:
        logger.error("移す行がありません")
        return 1

    print(describe(plan, source, args.to) + ("（dry-run）" if args.dry_run else ""))
    if args.dry_run:
        return 0

    if MoveDestination(args.at) is MoveDestination.TOP:
        repository.insert_rows_at(args.to, plan.insert_at, plan.row_count)
    else:
        repository.ensure_rows(args.to, max(plan.updates))
    repository.apply_updates(args.to, plan.updates)
    repository.delete_rows(source, sorted(plan.source_rows))

    logger.info(
        "行を移しました",
        extra={"context": {"source": source, "dest": args.to, "rows": plan.row_count}},
    )
    print(f"  → {source} から {len(plan.source_rows)}行を削除しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
