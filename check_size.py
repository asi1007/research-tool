from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.infrastructure.env import require_env
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.usecases.size_match import (
    Comparison,
    Dimension,
    Match,
    compare,
    extract_dimensions,
    pack_counts,
)

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)

VERDICT_LABEL = {
    Match.SAME: "一致",
    Match.PARTIAL: "一部だけ一致",
    Match.DIFFERENT: "不一致",
    Match.UNKNOWN: "判定不能（寸法が取れない）",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Amazon商品と仕入先候補の寸法が同じか突き合わせる")
    parser.add_argument("asin", help="Amazon の ASIN または商品URL")
    parser.add_argument("--supplier-text", help="1688側の規格名・商品説明。省略時は標準入力から読む")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def amazon_text(client: KeepaClient, asin: Asin) -> tuple[str, str]:
    product = client.fetch_product(asin)
    if product is None:
        raise LookupError(f"Keepa に商品がありません: {asin.value}")
    title = str(product.get("title") or "")
    features = "\n".join(str(f) for f in (product.get("features") or []))
    return title, features


def format_dimensions(dimensions: list[Dimension]) -> str:
    return " / ".join(
        f"{d.label}{d.millimeters:g}mm" if d.label else f"{d.millimeters:g}mm" for d in dimensions
    ) or "（取れず）"


def render(
    asin: Asin,
    amazon: list[Dimension],
    supplier: list[Dimension],
    result: Comparison,
    amazon_counts: list[int],
    supplier_counts: list[int],
) -> str:
    lines = [
        f"{asin.value}  判定: {VERDICT_LABEL[result.verdict]}",
        f"  Amazon : {format_dimensions(amazon)}",
        f"  仕入先 : {format_dimensions(supplier)}",
    ]
    for left, right in result.matched:
        mark = "=" if left == right else "≒"
        lines.append(f"    {left:g}mm {mark} {right:g}mm")
    for left in result.unmatched:
        lines.append(f"    {left:g}mm に対応する寸法が無い")
    if amazon_counts or supplier_counts:
        lines.append(f"  入数   : Amazon {amazon_counts or '-'} / 仕入先 {supplier_counts or '-'}")
    if result.verdict is Match.UNKNOWN:
        lines.append("  → 規格表・属性に寸法が無い。商品説明画像を読むこと")
    return "\n".join(lines)


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    asin = Asin.parse(args.asin)
    if asin is None:
        logger.error("ASIN として読めません", extra={"context": {"input": args.asin}})
        return 1

    supplier_raw = args.supplier_text if args.supplier_text is not None else sys.stdin.read()
    if not supplier_raw.strip():
        logger.error("仕入先側のテキストが空です")
        return 1

    client = KeepaClient(require_env("KEEPA_API_KEY"))
    title, features = amazon_text(client, asin)

    amazon = extract_dimensions(f"{title}\n{features}")
    supplier = extract_dimensions(supplier_raw)
    result = compare(amazon, supplier)
    amazon_counts = pack_counts(f"{title}\n{features}")
    supplier_counts = pack_counts(supplier_raw)

    if args.json:
        print(json.dumps({
            "asin": asin.value,
            "verdict": result.verdict.value,
            "amazon_mm": [d.millimeters for d in amazon],
            "supplier_mm": [d.millimeters for d in supplier],
            "matched": result.matched,
            "unmatched": result.unmatched,
            "amazon_counts": amazon_counts,
            "supplier_counts": supplier_counts,
        }, ensure_ascii=False))
    else:
        print(render(asin, amazon, supplier, result, amazon_counts, supplier_counts))

    return 0 if result.verdict in (Match.SAME, Match.PARTIAL) else 1


if __name__ == "__main__":
    raise SystemExit(main())
