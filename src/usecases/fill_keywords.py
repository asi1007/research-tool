from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_codes import ColumnCodes

HEADER_ROWS = 3
KEYWORD_COUNT = 3
# Ads API の bid は最小通貨単位（円の1/100）で返る
BID_UNITS_PER_YEN = 100
EXACT_MATCH = "EXACT"

ASIN_CODE = "ASIN_SELL"
KEYWORD_CODE = "NOTE_BUY_OTHER3"
BID_CODE = "NOTE_BUY_OTHER5"


@dataclass(frozen=True)
class KeywordSuggestion:
    keyword: str
    bid_yen: int


def _exact_bid(bid_info: list[dict]) -> int | None:
    for entry in bid_info:
        if entry.get("matchType") == EXACT_MATCH and entry.get("bid"):
            return round(entry["bid"] / BID_UNITS_PER_YEN)
    return None


def parse_recommendations(response: dict) -> list[KeywordSuggestion]:
    suggestions: list[KeywordSuggestion] = []

    for target in response.get("keywordTargetList") or []:
        keyword = str(target.get("keyword") or "").strip()
        bid_yen = _exact_bid(target.get("bidInfo") or [])
        if not keyword or bid_yen is None:
            continue
        suggestions.append(KeywordSuggestion(keyword=keyword, bid_yen=bid_yen))
        if len(suggestions) >= KEYWORD_COUNT:
            break

    return suggestions


def _cell(row: list, index: int) -> str:
    if index >= len(row):
        return ""
    return str(row[index]).strip()


def build_keyword_updates(
    values: list[list], asin: str, suggestions: list[KeywordSuggestion]
) -> dict[int, dict[int, object]]:
    codes = ColumnCodes(values)
    asin_index = codes.index_of(ASIN_CODE)
    keyword_index = codes.index_of(KEYWORD_CODE)
    bid_index = codes.index_of(BID_CODE)
    if not suggestions or asin_index is None or keyword_index is None or bid_index is None:
        return {}

    parsed = Asin.parse(asin)
    for offset, row in enumerate(values[HEADER_ROWS:]):
        if parsed is None or Asin.parse(_cell(row, asin_index)) != parsed:
            continue
        # 手入力の検索ワードを消さない
        if _cell(row, keyword_index) or _cell(row, bid_index):
            return {}
        return {
            HEADER_ROWS + offset + 1: {
                keyword_index: "\n".join(item.keyword for item in suggestions),
                bid_index: "\n".join(str(item.bid_yen) for item in suggestions),
            }
        }

    return {}
