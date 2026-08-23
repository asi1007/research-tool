from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin

MARKETPLACE_ID_JP = "A1VC38T7YXB528"
SPAPI_ENDPOINT_FE = "https://sellingpartnerapi-fe.amazon.com"
TOKEN_URL = "https://api.amazon.com/auth/o2/token"

_MM_PER_UNIT = {
    "millimeters": 1.0,
    "centimeters": 10.0,
    "inches": 25.4,
    "feet": 304.8,
}
_GRAMS_PER_UNIT = {
    "grams": 1.0,
    "kilograms": 1000.0,
    "pounds": 453.59237,
    "ounces": 28.349523125,
}


RETRYABLE_STATUS = (429, 500, 502, 503, 504)
MAX_RETRIES = 6
INITIAL_BACKOFF_SECONDS = 1.0

logger = logging.getLogger(__name__)


class SpApiError(RuntimeError):
    pass


class SpApiClient:
    def __init__(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        timeout: int = 60,
        session: object | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests
        self.sleep = sleep
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.marketplace_id = MARKETPLACE_ID_JP
        self.endpoint = SPAPI_ENDPOINT_FE
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise SpApiError(f"SP-API token error: {response.status_code} - {response.text[:200]}")

        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 3600) - 60
        return self._access_token

    def _request_with_retry(self, method: str, url: str, label: str, **kwargs) -> dict:
        backoff = INITIAL_BACKOFF_SECONDS

        for attempt in range(MAX_RETRIES):
            send = self.session.get if method == "get" else self.session.post
            response = send(url, timeout=self.timeout, **kwargs)

            if response.status_code == 200:
                return response.json()

            if response.status_code not in RETRYABLE_STATUS:
                raise SpApiError(
                    f"SP-API {label} error: {response.status_code} - {response.text[:200]}"
                )

            logger.warning(
                "SP-APIのスロットリングを待機",
                extra={
                    "context": {
                        "label": label,
                        "status": response.status_code,
                        "wait_seconds": backoff,
                        "attempt": attempt + 1,
                    }
                },
            )
            self.sleep(backoff)
            backoff *= 2

        raise SpApiError(f"SP-API {label} error: リトライ上限に到達しました")

    def fetch_catalog_item(self, asin: Asin) -> dict:
        return self._request_with_retry(
            "get",
            f"{self.endpoint}/catalog/2022-04-01/items/{asin}",
            label="catalog",
            params={
                "marketplaceIds": self.marketplace_id,
                "includedData": "attributes,dimensions,images,productTypes,salesRanks",
            },
            headers={"x-amz-access-token": self._get_access_token()},
        )

    def fetch_fees_estimate(self, asin: Asin, price: float) -> dict:
        return self._request_with_retry(
            "post",
            f"{self.endpoint}/products/fees/v0/items/{asin}/feesEstimate",
            label="fees",
            headers={
                "x-amz-access-token": self._get_access_token(),
                "Content-Type": "application/json",
            },
            json={
                "FeesEstimateRequest": {
                    "MarketplaceId": self.marketplace_id,
                    "PriceToEstimateFees": {
                        "ListingPrice": {"CurrencyCode": "JPY", "Amount": price}
                    },
                    "Identifier": str(asin),
                    "IsAmazonFulfilled": True,
                }
            },
        )

    @staticmethod
    def extract_catalog(response: dict) -> dict:
        attributes = response.get("attributes") or {}
        images = response.get("images") or []
        package = next(
            (d for d in response.get("dimensions") or [] if d.get("type") == "package"), {}
        )

        return {
            "title": SpApiClient._first_value(attributes.get("item_name")),
            "image_url": SpApiClient._first_image_link(images),
            "release_date": SpApiClient._extract_release_date(attributes),
            "size": ProductSize(
                length_mm=SpApiClient._to_mm(package.get("length")),
                width_mm=SpApiClient._to_mm(package.get("width")),
                height_mm=SpApiClient._to_mm(package.get("height")),
            ),
            "weight_grams": SpApiClient._to_grams(package.get("weight")),
        }

    @staticmethod
    def extract_fees(response: dict) -> dict:
        result = (response.get("payload") or {}).get("FeesEstimateResult") or {}
        if result.get("Status") != "Success":
            return {"referral_fee": 0, "fba_fee": 0}

        details = (result.get("FeesEstimate") or {}).get("FeeDetailList") or []
        fees = {"referral_fee": 0, "fba_fee": 0}
        for detail in details:
            amount = (detail.get("FeeAmount") or {}).get("Amount") or 0
            if detail.get("FeeType") == "ReferralFee":
                fees["referral_fee"] = amount
            elif detail.get("FeeType") in ("FBAFees", "VariableClosingFee"):
                fees["fba_fee"] += amount
        return fees

    @staticmethod
    def _extract_release_date(attributes: dict) -> str:
        for key in ("street_date", "product_site_launch_date"):
            if value := SpApiClient._first_value(attributes.get(key)):
                return value.split("T")[0]
        return ""

    @staticmethod
    def _first_value(entries: object) -> str:
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            return str(entries[0].get("value") or "")
        return ""

    @staticmethod
    def _first_image_link(images: list) -> str:
        for group in images:
            for image in group.get("images") or []:
                if link := image.get("link"):
                    return link
        return ""

    @staticmethod
    def _to_mm(dimension: object) -> float:
        if not isinstance(dimension, dict):
            return 0.0
        return (dimension.get("value") or 0) * _MM_PER_UNIT.get(dimension.get("unit"), 10.0)

    @staticmethod
    def _to_grams(weight: object) -> float:
        if not isinstance(weight, dict):
            return 0.0
        return (weight.get("value") or 0) * _GRAMS_PER_UNIT.get(weight.get("unit"), 1.0)
