from __future__ import annotations

from src.domain.entities.product_info import ProductInfo
from src.infrastructure.column_mapper import ColumnMapper

# 取得できた値が0でも書き込む項目。空欄のままだと未取得と区別できず毎回再取得されるため。
# 手数料は含めない。Amazonは販売時に必ず販売手数料を取るため0は正当な値になりえず、
# カート価格が無い・手数料APIが失敗したときの0を書くと利益が過大に出る。
ZERO_WRITABLE_FIELDS = frozenset({"buy_box_price", "monthly_sold", "international_shipping"})


class RowUpdatePlanner:
    def __init__(self, mapper: ColumnMapper, overwrite: bool) -> None:
        self.mapper = mapper
        self.overwrite = overwrite

    def needs_fetch(self, row: list) -> bool:
        if self.overwrite:
            return True
        return any(self._is_blank(row, field) for field in self.mapper.writable_fields())

    def plan(self, row: list, product: ProductInfo, international_shipping: int) -> dict[int, object]:
        if not product.is_fetched:
            return {}

        values = self._product_values(product, international_shipping)

        updates: dict[int, object] = {}
        for field, value in values.items():
            column = self.mapper.column_index(field)
            if column is None or not self._is_writable(field, value):
                continue
            if not self.overwrite and not self._is_blank(row, field):
                continue
            updates[column] = value
        return updates

    def _is_writable(self, field: str, value: object) -> bool:
        if field in ZERO_WRITABLE_FIELDS:
            return value is not None
        return bool(value)

    def _product_values(self, product: ProductInfo, international_shipping: int) -> dict[str, object]:
        return {
            "title": product.title,
            "image": product.image_formula,
            "release_date": product.release_date,
            "buy_box_price": product.buy_box_price,
            "monthly_sold": product.monthly_sold,
            "size_length": product.size.length_mm,
            "size_width": product.size.width_mm,
            "size_height": product.size.height_mm,
            "weight": product.weight_grams,
            "referral_fee": product.referral_fee,
            "fba_fee": product.fba_fee,
            "international_shipping": international_shipping,
        }

    def _is_blank(self, row: list, field: str) -> bool:
        column = self.mapper.column_index(field)
        if column is None:
            return False
        value = row[column] if column < len(row) else ""
        return str(value).strip() == ""
