from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import requests

from src.domain.entities.product_info import ProductInfo
from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin

KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
JAPAN_DOMAIN = 5
_YYYYMMDD = re.compile(r"^\d{8}$")
_BUY_BOX_CSV_KEYS = (18, 1, 0)
MAX_TOKEN_WAIT_SECONDS = 300.0
DEFAULT_TOKEN_WAIT_SECONDS = 60.0
MAX_TOKEN_RETRIES = 20

logger = logging.getLogger(__name__)


class KeepaApiError(RuntimeError):
    pass


class KeepaClient:
    def __init__(
        self,
        api_key: str,
        timeout: int = 60,
        session: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.keepa.com"
        self.session = session or requests
        self.sleep = sleep
        self.tokens_left: int | None = None

    def fetch_product(self, asin: Asin) -> dict:
        for attempt in range(MAX_TOKEN_RETRIES):
            response = self.session.get(
                f"{self.base_url}/product",
                params={"key": self.api_key, "domain": JAPAN_DOMAIN, "asin": str(asin), "stats": 1},
                timeout=self.timeout,
            )
            payload = self._decode(response)
            self.tokens_left = payload.get("tokensLeft", self.tokens_left)

            if self._is_token_depleted(response, payload):
                self._wait_for_refill(payload, asin, attempt)
                continue

            if response.status_code != 200:
                raise KeepaApiError(
                    f"Keepa API error: {response.status_code} - {response.text[:200]}"
                )

            products = payload.get("products") or []
            if not products:
                raise KeepaApiError(f"Product not found: {asin}")

            return products[0]

        raise KeepaApiError(f"Keepa token exhausted after {MAX_TOKEN_RETRIES} retries: {asin}")

    def fetch_refill_rate_per_minute(self) -> int | None:
        try:
            response = self.session.get(
                f"{self.base_url}/token",
                params={"key": self.api_key},
                timeout=self.timeout,
            )
            payload = self._decode(response)
        except Exception as error:
            logger.warning("Keepaの補充レート取得に失敗", extra={"context": {"error": str(error)}})
            return None

        self.tokens_left = payload.get("tokensLeft", self.tokens_left)
        refill_rate = payload.get("refillRate")
        return refill_rate if isinstance(refill_rate, int) and refill_rate > 0 else None

    @staticmethod
    def _decode(response: object) -> dict:
        try:
            payload = response.json()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _is_token_depleted(response: object, payload: dict) -> bool:
        if response.status_code == 429:
            return True
        return (payload.get("tokensLeft") or 0) < 0

    def _wait_for_refill(self, payload: dict, asin: Asin, attempt: int) -> None:
        refill_ms = payload.get("refillIn")
        seconds = (refill_ms / 1000) if refill_ms else DEFAULT_TOKEN_WAIT_SECONDS
        seconds = min(seconds, MAX_TOKEN_WAIT_SECONDS)

        logger.warning(
            "Keepaトークンが枯渇したため補充を待機",
            extra={
                "context": {
                    "asin": str(asin),
                    "wait_seconds": seconds,
                    "tokens_left": payload.get("tokensLeft"),
                    "attempt": attempt + 1,
                }
            },
        )
        self.sleep(seconds)

    @staticmethod
    def extract(asin: Asin, raw: dict) -> ProductInfo:
        return ProductInfo(
            asin=asin,
            title=raw.get("title") or "",
            image_url=KeepaClient._extract_main_image(raw),
            release_date=KeepaClient._extract_release_date(raw),
            size=ProductSize(
                length_mm=raw.get("packageLength") or 0,
                width_mm=raw.get("packageWidth") or 0,
                height_mm=raw.get("packageHeight") or 0,
            ),
            weight_grams=raw.get("packageWeight") or 0,
            buy_box_price=KeepaClient._extract_buy_box_price(raw),
            monthly_sold=raw.get("monthlySold") or 0,
        )

    @staticmethod
    def _extract_main_image(raw: dict) -> str:
        images = raw.get("images") or []
        if isinstance(images, list) and images:
            main = next(
                (i for i in images if isinstance(i, dict) and i.get("variant") == "MAIN"),
                images[0],
            )
            if isinstance(main, dict) and (file_name := main.get("l") or main.get("m")):
                return file_name

        # 旧レスポンス形式へのフォールバック（Keepaは imagesCSV を廃止済み）
        images_csv = raw.get("imagesCSV") or ""
        return images_csv.split(",")[0] if images_csv else ""

    @staticmethod
    def _extract_release_date(raw: dict) -> str:
        if (release_date := raw.get("releaseDate") or 0) > 0:
            return KeepaClient._from_keepa_minutes(release_date)
        if (publication_date := raw.get("publicationDate") or 0) > 0:
            return KeepaClient._from_yyyymmdd(publication_date)
        if (availability := raw.get("availabilityAmazon") or 0) > 0:
            return KeepaClient._from_keepa_minutes(availability)
        return ""

    @staticmethod
    def _extract_buy_box_price(raw: dict) -> float:
        if (from_stats := KeepaClient._price_from_stats(raw)) is not None:
            return from_stats

        csv = raw.get("csv") or {}
        for key in _BUY_BOX_CSV_KEYS:
            series = KeepaClient._csv_series(csv, key)
            if not series or len(series) < 2:
                continue
            latest = series[-1]
            if latest != -1:
                return latest
        return 0

    @staticmethod
    def _price_from_stats(raw: dict) -> float | None:
        current = (raw.get("stats") or {}).get("current") or []
        for key in _BUY_BOX_CSV_KEYS:
            if key < len(current) and current[key] not in (-1, None):
                return current[key]
        return None

    @staticmethod
    def _csv_series(csv: object, key: int) -> list | None:
        if isinstance(csv, dict):
            return csv.get(key)
        if isinstance(csv, (list, tuple)) and len(csv) > key:
            return csv[key]
        return None

    @staticmethod
    def _from_keepa_minutes(minutes: int) -> str:
        return (KEEPA_EPOCH + timedelta(minutes=minutes)).strftime("%Y-%m-%d")

    @staticmethod
    def _from_yyyymmdd(value: int) -> str:
        text = str(value)
        if not _YYYYMMDD.match(text):
            return text
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
