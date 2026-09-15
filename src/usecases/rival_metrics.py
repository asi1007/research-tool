from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum

# Keepa の stats.current の並び
BUY_BOX_INDEX = 18
NEW_INDEX = 1
RATING_INDEX = 16        # 10倍値（40 = 4.0）
REVIEW_COUNT_INDEX = 17  # /product に rating=1 を付けないと -1 のまま返る

# レビューが少ないうちは後発でも追いつける。多いと価格勝負になり中国輸入では勝てない
WEAK_REVIEW_COUNT = 50
STRONG_REVIEW_COUNT = 200
# 月に数個しか売れない商品は広告のターゲットにしても意味がない
MINOR_MONTHLY_SOLD = 30


class Strength(Enum):
    WEAK = "狙い目"
    STRONG = "強敵"
    MINOR = "小粒"
    UNKNOWN = "不明"


@dataclass(frozen=True)
class RivalMetric:
    asin: str
    title: str
    brand: str
    monthly_sold: int | None
    price: int | None
    review_count: int | None
    rating: float | None

    @property
    def monthly_revenue(self) -> int | None:
        return 月商(self.monthly_sold, self.price)

    @property
    def strength(self) -> Strength:
        if self.monthly_sold is None:
            return Strength.UNKNOWN
        if self.monthly_sold < MINOR_MONTHLY_SOLD:
            return Strength.MINOR
        reviews = self.review_count if self.review_count is not None else 0
        if reviews >= STRONG_REVIEW_COUNT:
            return Strength.STRONG
        if reviews <= WEAK_REVIEW_COUNT:
            return Strength.WEAK
        return Strength.UNKNOWN


def 月商(monthly_sold: int | None, price: int | None) -> int | None:
    if monthly_sold is None or price is None:
        return None
    return monthly_sold * price


def _positive(value: object) -> int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return int(value) if value >= 0 else None


def build_metric(product: dict) -> RivalMetric:
    current = ((product.get("stats") or {}).get("current") or [])
    get = lambda index: _positive(current[index]) if index < len(current) else None

    # 日本の価格は円そのままで返る（米国のようにセント単位ではない）
    raw_rating = get(RATING_INDEX)
    return RivalMetric(
        asin=str(product.get("asin") or ""),
        title=str(product.get("title") or "")[:46],
        brand=str(product.get("brand") or "-"),
        monthly_sold=_positive(product.get("monthlySold")),
        price=get(BUY_BOX_INDEX) or get(NEW_INDEX),
        review_count=get(REVIEW_COUNT_INDEX),
        rating=raw_rating / 10 if raw_rating else None,
    )


def rank_rivals(rivals: list[RivalMetric], limit: int | None = None) -> list[RivalMetric]:
    # 月商が取れない行は比較できないので末尾へ回す
    ordered = sorted(rivals, key=lambda r: (r.monthly_revenue is None, -(r.monthly_revenue or 0)))
    return ordered[:limit] if limit else ordered


def summarize(rivals: list[RivalMetric]) -> dict[str, object]:
    prices = [r.price for r in rivals if r.price is not None]
    reviews = [r.review_count for r in rivals if r.review_count is not None]
    revenues = [r.monthly_revenue for r in rivals if r.monthly_revenue is not None]

    return {
        "件数": len(rivals),
        "価格中央値": int(statistics.median(prices)) if prices else None,
        "レビュー中央値": int(statistics.median(reviews)) if reviews else None,
        "月商合計": sum(revenues) if revenues else None,
        "狙い目": sum(1 for r in rivals if r.strength is Strength.WEAK),
        "強敵": sum(1 for r in rivals if r.strength is Strength.STRONG),
    }
