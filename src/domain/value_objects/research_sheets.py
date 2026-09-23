from __future__ import annotations

import unicodedata

REJECTED_SHEET = "候補外"
SEASONAL_SHEET = "季節商品"
PENDING_SHEET = "保留"
# A列の印で行が移る先。移した行をまた拾うと往復し続けるので、候補タブには含めない
MARK_DESTINATION_SHEETS = (REJECTED_SHEET, SEASONAL_SHEET, PENDING_SHEET)
# 調査候補が並ばないタブ。ここに無いタブはすべて候補タブとして扱う
NON_CANDIDATE_SHEETS = ("リリース", "調査済み", "サンプル発注管理", "テンプレ(新)", "idea")


def _normalize(sheet: str) -> str:
    return unicodedata.normalize("NFKC", sheet.strip())


def candidate_sheets(sheet_titles: list[str]) -> list[str]:
    # タブ名のパターン（自動調査◯◯円）で選ぶと、価格帯を名乗らない「優先」のような候補タブが
    # 落ちる。実際に drop_marked がこれで「優先」を見ておらず、印が31件溜まった（2026-09-23）。
    # 候補タブは増えるが非候補タブは増えないので、対象ではなく対象外を並べる
    excluded = {_normalize(title) for title in (*MARK_DESTINATION_SHEETS, *NON_CANDIDATE_SHEETS)}
    return [title for title in sheet_titles if _normalize(title) not in excluded]
