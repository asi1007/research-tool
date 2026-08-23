from __future__ import annotations

import logging

from src.domain.entities.product_info import ProductInfo
from src.domain.repositories.product_data_source import KeepaDataSource, SpApiDataSource
from src.domain.value_objects.asin import Asin
from src.infrastructure.keepa_client import KeepaClient
from src.infrastructure.spapi_client import SpApiClient

logger = logging.getLogger(__name__)


class ProductInfoFetcher:
    def __init__(self, keepa: KeepaDataSource, spapi: SpApiDataSource) -> None:
        self.keepa = keepa
        self.spapi = spapi

    def fetch(self, asin: Asin) -> ProductInfo:
        product = self._fetch_from_keepa(asin)
        self._complement_from_spapi(asin, product)
        self._apply_fees(asin, product)
        return product

    def _fetch_from_keepa(self, asin: Asin) -> ProductInfo:
        try:
            return KeepaClient.extract(asin, self.keepa.fetch_product(asin))
        except Exception as error:
            logger.warning("Keepa取得失敗", extra={"context": {"asin": str(asin), "error": str(error)}})
            return ProductInfo(asin=asin)

    def _complement_from_spapi(self, asin: Asin, product: ProductInfo) -> None:
        try:
            catalog = SpApiClient.extract_catalog(self.spapi.fetch_catalog_item(asin))
        except Exception as error:
            logger.warning(
                "SP-APIカタログ取得失敗", extra={"context": {"asin": str(asin), "error": str(error)}}
            )
            return

        product.title = product.title or catalog["title"]
        product.image_url = product.image_url or catalog["image_url"]
        product.release_date = product.release_date or catalog["release_date"]
        if product.size.is_empty:
            product.size = catalog["size"]
        product.weight_grams = product.weight_grams or catalog["weight_grams"]

    def _apply_fees(self, asin: Asin, product: ProductInfo) -> None:
        if not product.buy_box_price or product.buy_box_price <= 0:
            logger.info("カート価格が無いため手数料計算をスキップ", extra={"context": {"asin": str(asin)}})
            return

        try:
            fees = SpApiClient.extract_fees(
                self.spapi.fetch_fees_estimate(asin, product.buy_box_price)
            )
        except Exception as error:
            logger.warning(
                "SP-API手数料取得失敗", extra={"context": {"asin": str(asin), "error": str(error)}}
            )
            return

        product.referral_fee = fees["referral_fee"]
        product.fba_fee = fees["fba_fee"]
