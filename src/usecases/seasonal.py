from __future__ import annotations

import unicodedata

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

HEADER_ROWS = 3
SEASONAL_SHEET = "季節商品"
ASIN_CODE = "ASIN_SELL"
TITLE_CODE = "TITLE_SELL"

# 夏物。冷房・冷却まわりは「冷蔵」「冷凍」と紛れるので、器具や用途まで含んだ語で拾う
SUMMER_KEYWORDS: tuple[str, ...] = (
    "日傘", "扇風機", "ファン", "冷感", "冷却プレート", "瞬間冷却", "ひんやり",
    "氷嚢", "氷のう", "保冷剤", "熱中症", "暑さ対策", "猛暑", "涼", "クーラー",
    "水着", "スイミング", "スイムゴーグル", "水中メガネ", "プール", "浮き輪",
    "うちわ", "虫よけ", "虫除け", "蚊取り", "蚊帳", "日焼け", "uvカット",
    "サンダル", "麦わら", "冷却タオル", "冷感タオル", "ネッククーラー",
)

# 冬物。既に季節商品タブへ入っているものに合わせる
WINTER_KEYWORDS: tuple[str, ...] = (
    "電熱", "ヒーター", "加熱パンツ", "湯たんぽ", "カイロ", "防寒", "あったか",
    "毛布", "こたつ", "加湿器", "結露", "雪かき", "スノー", "手袋", "マフラー",
)

SEASONAL_KEYWORDS: tuple[str, ...] = SUMMER_KEYWORDS + WINTER_KEYWORDS


def _normalize(title: str) -> str:
    return unicodedata.normalize("NFKC", title).lower()


def is_seasonal_title(title: str) -> bool:
    normalized = _normalize(title)
    if not normalized.strip():
        return False
    return any(_normalize(keyword) in normalized for keyword in SEASONAL_KEYWORDS)


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def seasonal_row_numbers(values: list[list]) -> list[int]:
    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    title_index = codes.index_of(TITLE_CODE)
    if asin_index is None or title_index is None:
        return []

    return [
        HEADER_ROWS + offset + 1
        for offset, row in enumerate(values[HEADER_ROWS:])
        if Asin.parse(_cell(row, asin_index)) is not None
        and is_seasonal_title(_cell(row, title_index))
    ]
