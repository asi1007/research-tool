from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.domain.entities.rival_candidate import RANKING, RELATED, SEARCH
from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import (
    CODE_ROW,
    DEFAULT_HEADER_ROW,
    GoogleSheetRepository,
    SheetTable,
    column_letter,
)
from src.usecases.rival_research import (
    build_rival_updates,
    is_raw_collect_output,
    merge_candidates,
    plan_column_insert,
    plan_rival_rows,
)

PROJECT_ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

RANK_CODE = "RIVAL_RANK"
RANK_HEADER = "順位"
RANK_AFTER_CODE = "TITLE_SELL"
ASIN_CODE = "ASIN_SELL"
KEYWORD_HEADER = "検索ワード"
SOURCES = (RELATED, SEARCH, RANKING)


@dataclass(frozen=True)
class RivalTarget:
    sheet: str
    row_number: int
    asin: str
    title: str
    keyword: str


def load_repository() -> GoogleSheetRepository:
    load_dotenv(PROJECT_ROOT / ".env")
    return GoogleSheetRepository(
        str(PROJECT_ROOT / require_env("SERVICE_ACCOUNT_FILE")),
        require_env("RESEARCH_SPREADSHEET_ID"),
    )


def normalize_header(label: object) -> str:
    return str(label or "").replace("\n", "").strip()


def find_target(repository: GoogleSheetRepository, asin: Asin) -> RivalTarget | None:
    for sheet, values in repository.read_all_values().items():
        if not values:
            continue
        codes = ColumnCodes(values)
        asin_index = codes.index_of(ASIN_CODE)
        if asin_index is None:
            continue

        headers = {normalize_header(h): i for i, h in enumerate(SheetTable(values).headers)}
        title_index = headers.get("商品名")
        keyword_index = headers.get(KEYWORD_HEADER)

        for offset, row in enumerate(values[DEFAULT_HEADER_ROW:]):
            cell = str(row[asin_index]) if asin_index < len(row) else ""
            if Asin.parse(cell) is None or Asin.parse(cell).value != asin.value:
                continue

            def read(index: int | None) -> str:
                if index is None or index >= len(row):
                    return ""
                return str(row[index]).strip()

            return RivalTarget(
                sheet=sheet,
                row_number=DEFAULT_HEADER_ROW + offset + 1,
                asin=asin.value,
                title=read(title_index),
                # 検索ワードは改行区切りで複数入る。1行目が最上位の推奨キーワード
                keyword=read(keyword_index).split("\n")[0].strip(),
            )
    return None


def ensure_rank_column(repository: GoogleSheetRepository, sheet: str) -> int:
    values = repository.read_values(sheet)
    codes = [str(c).strip() for c in values[CODE_ROW - 1]]
    index = plan_column_insert(codes, after_code=RANK_AFTER_CODE, new_code=RANK_CODE)
    if index is None:
        return codes.index(RANK_CODE)

    repository.insert_column_at(sheet, index, header=RANK_HEADER, code=RANK_CODE)
    return index


def run_target(args: argparse.Namespace) -> int:
    asin = Asin.parse(args.asin)
    if asin is None:
        print(json.dumps({"error": f"ASIN として読めません: {args.asin}"}, ensure_ascii=False))
        return 1

    repository = load_repository()
    target = find_target(repository, asin)
    if target is None:
        print(json.dumps({"error": f"{asin.value} の行が見つかりません"}, ensure_ascii=False))
        return 1

    logger.info("対象行を特定しました", extra={"context": asdict(target)})
    print(json.dumps(asdict(target), ensure_ascii=False, indent=1))
    return 0


def run_collect(args: argparse.Namespace) -> int:
    from src.infrastructure.rival_scraper import RivalScraper

    asin = Asin.parse(args.asin)
    if asin is None:
        print(f"ASIN として読めません: {args.asin}", file=sys.stderr)
        return 1

    repository = load_repository()
    target = find_target(repository, asin)
    if target is None:
        print(f"{asin.value} の行が見つかりません", file=sys.stderr)
        return 1
    if not target.keyword:
        print(
            "J列『検索ワード』が空です。fill_keywords.py を先に流してください",
            file=sys.stderr,
        )
        return 1

    scraper = RivalScraper(headless=not args.headed)
    collected = asyncio.run(scraper.collect(asin.value, target.keyword, limit=args.depth))

    payload = {"asin": asin.value, "title": target.title, "keyword": target.keyword, **collected}
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        print(f"{args.out} へ書き出しました")
        for source in SOURCES:
            print(f"\n[{source}] {len(payload[source])}件")
            for item in payload[source]:
                own = "  ← 自社" if item["asin"] == asin.value else ""
                print(f"  {item['rank']:>3}  {item['asin']}  {item['title'][:44]}{own}")
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=1))
    return 0


def run_write(args: argparse.Namespace) -> int:
    asin = Asin.parse(args.asin)
    if asin is None:
        print(f"ASIN として読めません: {args.asin}", file=sys.stderr)
        return 1

    payload = json.loads(Path(args.candidates).read_text())
    if is_raw_collect_output(payload) and not args.allow_raw:
        print(
            "collect の生出力をそのまま渡しています。ほぼ同一の候補だけ残した JSON を作ってください"
            "（意図してそのまま使うなら --allow-raw）",
            file=sys.stderr,
        )
        return 1
    sources = {
        source: [
            (item.get("asin"), item.get("title", ""), item.get("rank"))
            for item in payload.get(source) or []
        ]
        for source in SOURCES
    }
    candidates = merge_candidates(sources, exclude=asin, limit_per_source=args.limit)
    if not candidates:
        print("候補がありません（書き込みませんでした）", file=sys.stderr)
        return 1

    repository = load_repository()
    target = find_target(repository, asin)
    if target is None:
        print(f"{asin.value} の行が見つかりません", file=sys.stderr)
        return 1

    rank_index = ensure_rank_column(repository, target.sheet)
    # 列を足すと行の中身は変わらないが、念のため行番号を引き直してから挿入する
    target = find_target(repository, asin)
    values = repository.read_values(target.sheet)
    asin_index = ColumnCodes(values).index_of(ASIN_CODE)

    plan = plan_rival_rows(target.row_number, len(candidates))
    if args.dry_run:
        for candidate in candidates:
            print(f"{candidate.rank_label().replace(chr(10), ' / '):<28} {candidate.asin} {candidate.title}")
        print(f"\n{target.sheet} {target.row_number}行の下へ {len(candidates)}行 挿入（順位列 {column_letter(rank_index)}）")
        return 0

    repository.insert_rows_at(target.sheet, plan["start_row"], plan["count"])
    updates = build_rival_updates(
        candidates, base_row=target.row_number, asin_column=asin_index, rank_column=rank_index
    )
    repository.apply_updates(target.sheet, updates)

    logger.info(
        "ライバル候補を書き込みました",
        extra={
            "context": {
                "sheet": target.sheet,
                "base_row": target.row_number,
                "rows": len(candidates),
                "asins": [c.asin.value for c in candidates],
            }
        },
    )
    print(f"{target.sheet} {target.row_number}行の下へ {len(candidates)}行 書き込みました")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ライバル商品調査")
    parser.add_argument("--debug", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    target = sub.add_parser("target", help="ASIN の行・検索ワードを調べる")
    target.add_argument("asin")
    target.set_defaults(func=run_target)

    collect = sub.add_parser("collect", help="3経路をブラウザで読んで候補を出す")
    collect.add_argument("asin")
    collect.add_argument("--out", help="書き出す JSON のパス")
    collect.add_argument("--depth", type=int, default=12, help="経路ごとに読む件数（既定 12）")
    collect.add_argument("--headed", action="store_true", help="ブラウザを表示して実行する")
    collect.set_defaults(func=run_collect)

    write = sub.add_parser("write", help="収集した候補を行として挿入する")
    write.add_argument("asin")
    write.add_argument("--candidates", required=True, help="経路ごとの候補を入れた JSON")
    write.add_argument("--limit", type=int, default=3, help="経路ごとの採用件数（既定 3）")
    write.add_argument("--allow-raw", action="store_true", help="collect の生出力をそのまま使う")
    write.add_argument("--dry-run", action="store_true")
    write.set_defaults(func=run_write)

    args = parser.parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
