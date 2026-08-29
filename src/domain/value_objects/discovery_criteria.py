from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
MIN_PER_PAGE = 50

# 中国輸入で扱えないルートカテゴリ。IDは Keepa /category（domain=5）で取得したもの
EXCLUDED_ROOT_CATEGORIES: tuple[int, ...] = (
    465392,      # 本
    52033011,    # 洋書
    561956,      # ミュージック
    561958,      # DVD
    2128134051,  # デジタルミュージック
    2250738051,  # Kindleストア
    2351649051,  # Prime Video
    2381130051,  # アプリ＆ゲーム
    4788676051,  # Alexaスキル
    637392,      # PCソフト
    637394,      # ゲーム
    2320455051,  # ファイナンス
    4976279051,  # Amazonデバイス・アクセサリ
    160384011,   # ドラッグストア
    57239051,    # 食品・飲料・お酒
    344845011,   # ベビー＆マタニティ
    2277724051,  # 大型家電
    3210981,     # 家電＆カメラ
)

STANDARD_PRODUCT_TYPE = 0
NO_AMAZON_OFFER = -1


def to_keepa_minutes(moment: datetime) -> int:
    return int((moment - KEEPA_EPOCH).total_seconds() // 60)


@dataclass(frozen=True)
class DiscoveryCriteria:
    max_price_yen: int = 1000
    min_monthly_sold: int = 1000
    max_age_days: int = 180
    excluded_categories: tuple[int, ...] = field(default=EXCLUDED_ROOT_CATEGORIES)
    per_page: int = MIN_PER_PAGE

    def __post_init__(self) -> None:
        if self.per_page < MIN_PER_PAGE:
            raise ValueError(f"perPage は {MIN_PER_PAGE} 以上にする（Keepa が 400 を返す）")

    def selection(self, now: datetime, page: int = 0) -> dict:
        listed_since = now - timedelta(days=self.max_age_days)
        return {
            "current_NEW_gte": 1,
            "current_NEW_lte": self.max_price_yen,
            "monthlySold_gte": self.min_monthly_sold,
            "listedSince_gte": to_keepa_minutes(listed_since),
            "productType": [STANDARD_PRODUCT_TYPE],
            "availabilityAmazon": [NO_AMAZON_OFFER],
            "categories_exclude": list(self.excluded_categories),
            "sort": [["monthlySold", "desc"]],
            "perPage": self.per_page,
            "page": page,
        }
