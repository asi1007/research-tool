from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

from dotenv import load_dotenv

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_band import band_for_price
from src.infrastructure.env import require_env
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.sheet_repository import GoogleSheetRepository
from src.usecases.discover_products import known_asins, plan_append

logger = logging.getLogger("add_asins")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="指定したASINを、価格に合う自動調査タブへ積む（価格帯はタブ名から読む）"
    )
    parser.add_argument("asins", nargs="+", help="ASIN または Amazon の商品URL")
    parser.add_argument("--sheet", help="タブを指定する。省略時は価格から選ぶ")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _parse_asins(raw: list[str]) -> list[Asin]:
    parsed = []
    for value in raw:
        asin = Asin.parse(value)
        if asin is None:
            raise SystemExit(f"ASINとして読めません: {value}")
        parsed.append(asin)
    return parsed


def _prices(keepa: KeepaClient, asins: list[Asin]) -> dict[str, int]:
    return {
        str(product.asin): int(product.buy_box_price)
        for product in keepa.fetch_products(asins)
        if product.buy_box_price
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(logging.INFO)
    load_dotenv()

    asins = _parse_asins(args.asins)
    repository = GoogleSheetRepository(
        require_env("SERVICE_ACCOUNT_FILE"), require_env("RESEARCH_SPREADSHEET_ID")
    )
    titles = repository.sheet_titles()

    if args.sheet:
        destinations = {args.sheet: asins}
        prices: dict[str, int] = {}
    else:
        prices = _prices(KeepaClient(require_env("KEEPA_API_KEY")), asins)
        destinations = {}
        for asin in asins:
            price = prices.get(str(asin))
            if price is None:
                logger.warning("価格が取れないので飛ばします", extra={"context": {"asin": str(asin)}})
                continue
            band = band_for_price(titles, price)
            if band is None:
                logger.warning(
                    "価格に合うタブがありません",
                    extra={"context": {"asin": str(asin), "price_yen": price}},
                )
                continue
            destinations.setdefault(band.sheet, []).append(asin)

    # 既に載っている ASIN を二重に積まない。どのタブにあってもスキップする。
    # 読んだ値は書き込みにも使い回す。タブを二度読むと 60req/分 のクォータに当たる
    sheet_values = {title: repository.read_values(title) for title in titles}
    already = known_asins(sheet_values)

    report = []
    for sheet, targets in destinations.items():
        fresh = [asin for asin in targets if str(asin) not in already]
        skipped = [str(asin) for asin in targets if str(asin) in already]
        entry = {
            "sheet": sheet,
            "added": [str(a) for a in fresh],
            "already_listed": skipped,
            "prices": {str(a): prices.get(str(a)) for a in targets},
        }
        report.append(entry)
        if args.dry_run or not fresh:
            continue

        plan = plan_append(sheet_values[sheet], fresh, date.today())
        if plan.rows_to_add:
            repository.ensure_rows(sheet, max(plan.updates))
        entry["cells"] = repository.apply_updates(sheet, plan.updates)
        entry["rows"] = sorted(plan.updates)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
