from __future__ import annotations

from src.domain.entities.product_size import ProductSize

DEFAULT_CNY_TO_JPY_RATE = 21.0
DEFAULT_RATE_PER_KG_CNY = 7.0


class InternationalShippingCalculator:
    def __init__(self, rate_per_kg_cny: float, cny_to_jpy_rate: float) -> None:
        self.rate_per_kg_cny = rate_per_kg_cny
        self.cny_to_jpy_rate = cny_to_jpy_rate

    def calculate(self, size: ProductSize, weight_grams: float) -> int:
        chargeable_weight_kg = max(size.volumetric_weight_kg, (weight_grams or 0) / 1000)
        shipping_cost_cny = chargeable_weight_kg * self.rate_per_kg_cny
        return round(shipping_cost_cny * self.cny_to_jpy_rate)
