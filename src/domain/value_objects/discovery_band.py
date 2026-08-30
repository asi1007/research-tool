from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.domain.value_objects.discovery_criteria import DiscoveryCriteria

SHEET_PREFIX = "自動調査"
DEFAULT_DISCOVERY_SHEET = "自動調査1000円以下"

# タブ名は全角数字・全角ハイフンで書かれていることがあるため NFKC で畳んでから読む
UPPER_ONLY_PATTERN = re.compile(rf"^{SHEET_PREFIX}(\d+)円以下$")
RANGE_PATTERN = re.compile(rf"^{SHEET_PREFIX}(\d+)円-(\d+)円$")
LOWER_ONLY_PATTERN = re.compile(rf"^{SHEET_PREFIX}(\d+)円以上$")


def _normalize(sheet: str) -> str:
    return unicodedata.normalize("NFKC", sheet.strip()).replace("ー", "-").replace("〜", "-")


@dataclass(frozen=True)
class DiscoveryBand:
    NO_UPPER_LIMIT_YEN = 1_000_000

    sheet: str
    min_price_yen: int
    max_price_yen: int

    @classmethod
    def from_sheet_name(cls, sheet: str) -> DiscoveryBand:
        normalized = _normalize(sheet)
        bounds = cls._parse_bounds(normalized)
        if bounds is None:
            raise ValueError(f"タブ名から価格帯を読み取れない: {sheet}")

        min_price_yen, max_price_yen = bounds
        if min_price_yen > max_price_yen:
            raise ValueError(f"タブ名の価格の下限が上限を超えている: {sheet}")

        return cls(sheet=sheet, min_price_yen=min_price_yen, max_price_yen=max_price_yen)

    @classmethod
    def _parse_bounds(cls, normalized: str) -> tuple[int, int] | None:
        upper_only = UPPER_ONLY_PATTERN.match(normalized)
        if upper_only:
            return 1, int(upper_only.group(1))

        price_range = RANGE_PATTERN.match(normalized)
        if price_range:
            return int(price_range.group(1)) + 1, int(price_range.group(2))

        lower_only = LOWER_ONLY_PATTERN.match(normalized)
        if lower_only:
            return int(lower_only.group(1)) + 1, cls.NO_UPPER_LIMIT_YEN

        return None

    def criteria(self) -> DiscoveryCriteria:
        return DiscoveryCriteria(
            min_price_yen=self.min_price_yen,
            max_price_yen=self.max_price_yen,
        )


def discovery_sheets(sheet_titles: list[str]) -> list[str]:
    bands: list[DiscoveryBand] = []

    for title in sheet_titles:
        try:
            bands.append(DiscoveryBand.from_sheet_name(title))
        except ValueError:
            continue

    return [band.sheet for band in sorted(bands, key=lambda band: band.min_price_yen)]
