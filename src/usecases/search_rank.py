from __future__ import annotations

import unicodedata
from datetime import date, timedelta

from src.infrastructure.column_codes import ColumnCodes

HEADER_ROWS = 3
KEYWORD_CODE = "NOTE_BUY_OTHER3"
RANK_CODE = "SEARCH_RANK"
SUNDAY = 6


def last_sunday(today: date, weeks_ago: int = 2) -> date:
    # Brand Analytics の週次レポートは dataStartTime が日曜でないと FATAL になる
    days_since_sunday = (today.weekday() - SUNDAY) % 7
    return today - timedelta(days=days_since_sunday + 7 * weeks_ago)


def normalize_term(term: str) -> str:
    return unicodedata.normalize("NFKC", term).strip().lower()


def build_rank_index(report: dict) -> dict[str, int]:
    index: dict[str, int] = {}

    for entry in report.get("dataByDepartmentAndSearchTerm") or []:
        term = normalize_term(str(entry.get("searchTerm") or ""))
        rank = entry.get("searchFrequencyRank")
        if not term or rank is None:
            continue
        index.setdefault(term, int(rank))

    return index


def lookup_ranks(keywords: list[str], index: dict[str, int]) -> list[str]:
    ranks = [str(index.get(normalize_term(keyword), "")) for keyword in keywords]
    return ranks if any(ranks) else []


def _cell(row: list, position: int) -> str:
    if position >= len(row):
        return ""
    return str(row[position]).strip()


def build_rank_updates(values: list[list], index: dict[str, int]) -> dict[int, dict[int, object]]:
    codes = ColumnCodes(values)
    keyword_index = codes.index_of(KEYWORD_CODE)
    rank_index = codes.index_of(RANK_CODE)
    if keyword_index is None or rank_index is None:
        return {}

    updates: dict[int, dict[int, object]] = {}
    for offset, row in enumerate(values[HEADER_ROWS:]):
        keywords = _cell(row, keyword_index)
        if not keywords or _cell(row, rank_index):
            continue

        ranks = lookup_ranks(keywords.splitlines(), index)
        if not ranks:
            continue
        updates[HEADER_ROWS + offset + 1] = {rank_index: "\n".join(ranks)}

    return updates
