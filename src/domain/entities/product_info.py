from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.entities.product_size import ProductSize
from src.domain.value_objects.asin import Asin


@dataclass
class ProductInfo:
    asin: Asin
    title: str = ""
    image_url: str = ""
    release_date: str = ""
    size: ProductSize = field(default_factory=ProductSize)
    weight_grams: float = 0.0
    referral_fee: float = 0.0
    fba_fee: float = 0.0
    buy_box_price: float = 0.0
    monthly_sold: int = 0

    @property
    def is_fetched(self) -> bool:
        return bool(self.title or self.image_url)

    @property
    def image_formula(self) -> str:
        if not self.image_url:
            return ""
        full_url = (
            self.image_url
            if self.image_url.startswith("http")
            else f"https://m.media-amazon.com/images/I/{self.image_url}"
        )
        return f'=HYPERLINK("{self.asin.amazon_url}", IMAGE("{full_url}"))'
