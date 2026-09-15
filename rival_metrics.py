from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.infrastructure.env import require_env
from src.infrastructure.logging_config import configure_logging
from src.usecases.rival_metrics import RivalMetric, build_metric, rank_rivals, summarize

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

KEEPA_BATCH = 100  # /product は 100 ASIN までまとめて引ける。1 ASIN 1トークン
ASIN_PATTERN = re.compile(r"\b(B0[A-Z0-9]{8})\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="競合ASINに月販・価格・レビューを付けて、どれが強敵かを出す（Keepaのみ／追加費用なし）"
    )
    parser.add_argument("asins", nargs="*", help="競合ASIN。省略時は標準入力から拾う")
    parser.add_argument("--limit", type=int, default=20, help="表示件数（既定20）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def collect_asins(args: argparse.Namespace) -> list[str]:
    raw = " ".join(args.asins) if args.asins else sys.stdin.read()
    seen, found = set(), []
    for match in ASIN_PATTERN.findall(raw):
        asin = Asin.parse(match)
        if asin and asin.value not in seen:
            seen.add(asin.value)
            found.append(asin.value)
    return found


def fetch_products(api_key: str, asins: list[str]) -> list[dict]:
    products: list[dict] = []
    for start in range(0, len(asins), KEEPA_BATCH):
        chunk = asins[start : start + KEEPA_BATCH]
        url = (
            f"https://api.keepa.com/product?key={api_key}&domain=5"
            f"&asin={','.join(chunk)}&stats=1&history=0&rating=1"
        )
        raw = urllib.request.urlopen(url).read()
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
        payload = json.loads(raw)
        products.extend(payload.get("products") or [])
        logger.info(
            "Keepaから取得しました",
            extra={"context": {"count": len(chunk), "tokens_left": payload.get("tokensLeft")}},
        )
    return products


def render(rivals: list[RivalMetric], summary: dict[str, object]) -> str:
    lines = [
        f"{'ASIN':<12} {'月商':>9} {'月販':>5} {'価格':>6} {'評価':>4} {'レビュー':>6}  強さ  商品名",
        "-" * 96,
    ]
    for r in rivals:
        revenue = f"{r.monthly_revenue:,}" if r.monthly_revenue is not None else "-"
        lines.append(
            f"{r.asin:<12} {revenue:>9} {r.monthly_sold or '-':>5} {r.price or '-':>6} "
            f"{r.rating or '-':>4} {r.review_count if r.review_count is not None else '-':>6}"
            f"  {r.strength.value:<4}  {r.title}"
        )
    lines.append("")
    lines.append(
        f"件数 {summary['件数']} / 価格中央値 {summary['価格中央値']}円 / "
        f"レビュー中央値 {summary['レビュー中央値']} / "
        f"月商合計 {summary['月商合計']:,}円" if summary["月商合計"] else f"件数 {summary['件数']}"
    )
    lines.append(f"狙い目（レビュー50以下で月販30以上） {summary['狙い目']}件 / 強敵（レビュー200以上） {summary['強敵']}件")
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    asins = collect_asins(args)
    if not asins:
        logger.error("ASIN が見つかりません")
        return 1

    products = fetch_products(require_env("KEEPA_API_KEY"), asins)
    rivals = rank_rivals([build_metric(p) for p in products], limit=args.limit)
    summary = summarize(rivals)

    if args.json:
        print(json.dumps({
            "summary": summary,
            "rivals": [
                {
                    "asin": r.asin, "title": r.title, "brand": r.brand,
                    "monthly_sold": r.monthly_sold, "price": r.price,
                    "monthly_revenue": r.monthly_revenue,
                    "review_count": r.review_count, "rating": r.rating,
                    "strength": r.strength.value,
                }
                for r in rivals
            ],
        }, ensure_ascii=False, indent=1))
    else:
        print(render(rivals, summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
