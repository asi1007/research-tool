from __future__ import annotations

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "asin": ("ASIN",),
    "title": ("商品名",),
    "image": ("画像URL", "商品画像"),
    "release_date": ("発売日",),
    "buy_box_price": ("カート価格",),
    "monthly_sold": ("販売数/FBA数",),
    "size_length": ("サイズ（長さ）", "サイズ(長さ)"),
    "size_width": ("サイズ(幅)", "サイズ（幅）"),
    "size_height": ("サイズ(高さ)", "サイズ（高さ）"),
    "weight": ("重量",),
    "referral_fee": ("販売手数料",),
    "fba_fee": ("配送代行手数料（FBA手数料）", "FBA手数料+成約料"),
    "international_shipping": ("国際送料",),
}

WRITABLE_FIELDS: tuple[str, ...] = tuple(f for f in FIELD_ALIASES if f != "asin")


def normalize_header(header: object) -> str:
    return str(header or "").replace("\n", "").strip()


class ColumnMapper:
    def __init__(self, headers: list[str]) -> None:
        self.headers = [normalize_header(h) for h in headers]
        self._resolved = {
            field: self._resolve(aliases) for field, aliases in FIELD_ALIASES.items()
        }

    def _resolve(self, aliases: tuple[str, ...]) -> int | None:
        for alias in aliases:
            if alias in self.headers:
                return self.headers.index(alias)
        return None

    def column_index(self, field: str) -> int | None:
        return self._resolved.get(field)

    def writable_fields(self) -> list[str]:
        return [f for f in WRITABLE_FIELDS if self._resolved.get(f) is not None]
