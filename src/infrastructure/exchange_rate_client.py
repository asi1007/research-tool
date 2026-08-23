from __future__ import annotations

import logging

import requests

from src.infrastructure.shipping_calculator import DEFAULT_CNY_TO_JPY_RATE

logger = logging.getLogger(__name__)
EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/CNY"


def fetch_cny_to_jpy_rate(timeout: int = 30) -> float:
    try:
        response = requests.get(EXCHANGE_RATE_URL, timeout=timeout)
        response.raise_for_status()
        return float(response.json()["rates"]["JPY"])
    except Exception as error:
        logger.warning(
            "為替レート取得に失敗したためデフォルト値を使用",
            extra={"context": {"default": DEFAULT_CNY_TO_JPY_RATE, "error": str(error)}},
        )
        return DEFAULT_CNY_TO_JPY_RATE
