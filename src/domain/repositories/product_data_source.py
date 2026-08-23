from __future__ import annotations

from typing import Protocol

from src.domain.value_objects.asin import Asin


class KeepaDataSource(Protocol):
    def fetch_product(self, asin: Asin) -> dict: ...


class SpApiDataSource(Protocol):
    def fetch_catalog_item(self, asin: Asin) -> dict: ...

    def fetch_fees_estimate(self, asin: Asin, price: float) -> dict: ...
