from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

from src.infrastructure.alibaba_scraper import DEFAULT_VARIANT_OFFERS, CaptchaError, collect
from src.infrastructure.logging_config import configure_logging

PROJECT_ROOT = Path(__file__).resolve().parent
IMAGE_DIR = PROJECT_ROOT / "data" / "supplier_images"
EXIT_CAPTCHA = 2

logger = logging.getLogger("find_supplier_search")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="1688 の画像検索と規格表を playwright で取ってJSONで返す（判断はしない）"
    )
    parser.add_argument("--asin", required=True, help="Amazon の ASIN（画像の保存名に使う）")
    parser.add_argument("--image-url", help="商品画像のURL。省略時は data/supplier_images/<ASIN>.jpg を使う")
    parser.add_argument(
        "--variant-offers",
        type=int,
        default=DEFAULT_VARIANT_OFFERS,
        help=f"規格表まで開く候補の数（既定 {DEFAULT_VARIANT_OFFERS}）",
    )
    parser.add_argument("--debug", action="store_true", help="DEBUGログを出力する")
    return parser.parse_args(argv)


def ensure_image(asin: str, image_url: str | None) -> Path:
    path = IMAGE_DIR / f"{asin}.jpg"
    if path.exists():
        return path
    if not image_url:
        raise FileNotFoundError(f"画像がありません: {path}")
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(image_url, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def run(args: argparse.Namespace) -> int:
    try:
        image_path = ensure_image(args.asin, args.image_url)
    except (OSError, FileNotFoundError) as error:
        logger.error("画像を用意できません", extra={"context": {"asin": args.asin, "error": str(error)}})
        return 1

    try:
        result = collect(image_path, variant_offers=args.variant_offers)
    except CaptchaError as error:
        # キャプチャは人が通すしかない。呼び出し側が止まれるよう専用の終了コードで返す
        logger.error("CAPTCHA_STOP", extra={"context": {"asin": args.asin, "error": str(error)}})
        return EXIT_CAPTCHA

    result["asin"] = args.asin
    print(json.dumps(result, ensure_ascii=False, indent=1))
    logger.info(
        "候補を取りました",
        extra={"context": {"asin": args.asin, "count": len(result["candidates"])}},
    )
    return 0


def main() -> int:
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
