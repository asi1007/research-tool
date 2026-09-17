from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import ceil

KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)
MIN_PER_PAGE = 50
DEFAULT_MAX_AGE_DAYS = 365

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
    52374051,    # ビューティー（化粧品は薬機法で輸入できない。メイク道具等の雑貨も巻き添えで落ちる）
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

# ルート単位で落とせないもの。ポケモンカード等のトレカは「ホビー」配下にあり、
# ホビーごと除外するとプラモデル・鉄道模型まで落ちてしまう
EXCLUDED_SUB_CATEGORIES: tuple[int, ...] = (
    2189358051,   # ホビー > コレクションカード・アクセサリ（ポケモンカード・オリパ）
    10345415051,  # トレーディングカードゲーム
)

EXCLUDED_CATEGORIES: tuple[int, ...] = EXCLUDED_ROOT_CATEGORIES + EXCLUDED_SUB_CATEGORIES

# 1688 に同款が無いブランド。Keepa のクエリでは絞れないので商品名で弾く
# 1688 に同款が無く、中国輸入の競合にもならないブランド。
# 市場調査（自動調査タブへ積むか）とライバル調査（比較対象にするか）の両方で弾く。
# 英語表記は誤爆しやすい短い綴り（lec / muji 等）を入れない。
EXCLUDED_BRANDS: tuple[str, ...] = (
    "タカラトミー",
    "takara tomy",
    "オムロン",
    "omron",
    "コールマン",
    "coleman",
    # 日本の生活雑貨メーカー。自社ブランド品なので同じ棚に並んでも競合にならない
    "レック",
    "ダルトン",
    "dulton",
    "山崎実業",
    "山崎産業",
    "yamazaki",
    "無印良品",
    "マーナ",
    "marna",
    "アイリスオーヤマ",
    "iris ohyama",
    "ニトリ",
    "貝印",
    "パール金属",
)

# 有名ブランド。Keepa のブランド欄・メーカー欄だけで照合し、商品名では探さない。
# 商品名では「サーモス 交換用部品」「ゼブラ柄」のように互換品や柄の説明と区別できないため。
# 2026-09-17 にユーザーが d を付けて候補外にした商品のブランドが起点
EXCLUDED_MAKERS: tuple[str, ...] = (
    "トンボ",
    "tombow",
    "トンボ鉛筆",
    "ゼブラ",
    "zebra",
    "パイロット",
    "pilot",
    "ぺんてる",
    "pentel",
    "三菱鉛筆",
    "コクヨ",
    "kokuyo",
    "パナソニック",
    "panasonic",
    "zippo",
    "エンスカイ",
    "ensky",
    "ikea",
    "イケア",
    "テルモ",
    "ミカサ",
    "mikasa",
    "サーモス",
    "thermos",
    "スリーエム",
    "3m",
    "ニチバン",
    "nichiban",
)

STANDARD_PRODUCT_TYPE = 0
NO_AMAZON_OFFER = -1


def to_keepa_minutes(moment: datetime) -> int:
    return int((moment - KEEPA_EPOCH).total_seconds() // 60)


@dataclass(frozen=True)
class DiscoveryCriteria:
    min_price_yen: int = 1
    max_price_yen: int = 1000
    min_monthly_revenue_yen: int = 500_000
    # None は出品からの経過を問わない。古い商品は国内ブランド品が大半になる
    max_age_days: int | None = DEFAULT_MAX_AGE_DAYS
    excluded_categories: tuple[int, ...] = field(default=EXCLUDED_CATEGORIES)
    per_page: int = MIN_PER_PAGE

    def __post_init__(self) -> None:
        if self.min_price_yen > self.max_price_yen:
            raise ValueError(
                f"価格の下限が上限を超えている: {self.min_price_yen} > {self.max_price_yen}"
            )
        if self.per_page < MIN_PER_PAGE:
            raise ValueError(f"perPage は {MIN_PER_PAGE} 以上にする（Keepa が 400 を返す）")
        if self.max_age_days is not None and self.max_age_days < 1:
            raise ValueError(f"出品からの経過日数は1以上にする: {self.max_age_days}")

    def min_monthly_sold(self) -> int:
        # Keepa は「販売数×価格」で絞れない。帯の上限価格でも月商に届かない販売数を足切りに使う
        return ceil(self.min_monthly_revenue_yen / self.max_price_yen)

    def meets_revenue(self, price_yen: float, monthly_sold: int) -> bool:
        return price_yen * monthly_sold >= self.min_monthly_revenue_yen

    def selection(self, now: datetime, page: int = 0) -> dict:
        return {
            "current_NEW_gte": self.min_price_yen,
            "current_NEW_lte": self.max_price_yen,
            "monthlySold_gte": self.min_monthly_sold(),
            **self._listed_since(now),
            "productType": [STANDARD_PRODUCT_TYPE],
            "availabilityAmazon": [NO_AMAZON_OFFER],
            "categories_exclude": list(self.excluded_categories),
            "sort": [["monthlySold", "desc"]],
            "perPage": self.per_page,
            "page": page,
        }

    def _listed_since(self, now: datetime) -> dict:
        if self.max_age_days is None:
            return {}
        return {"listedSince_gte": to_keepa_minutes(now - timedelta(days=self.max_age_days))}
