from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.asin import Asin

RELATED = "関連"
SEARCH = "検索"
RANKING = "ランキング"
# 行の並び順と順位ラベルの並び順を決める。商品ページ→検索→ランキングの順に見る
SOURCE_ORDER = (RELATED, SEARCH, RANKING)


@dataclass(frozen=True)
class RivalPlacement:
    source: str
    rank: int

    def label(self) -> str:
        return f"{self.source}{self.rank}"


@dataclass(frozen=True)
class RivalCandidate:
    asin: Asin
    title: str
    placements: tuple[RivalPlacement, ...]

    def rank_label(self) -> str:
        ordered = sorted(self.placements, key=lambda p: (SOURCE_ORDER.index(p.source), p.rank))
        return "\n".join(placement.label() for placement in ordered)

    def sort_key(self) -> tuple[int, int]:
        ordered = sorted(self.placements, key=lambda p: (SOURCE_ORDER.index(p.source), p.rank))
        first = ordered[0]
        return (SOURCE_ORDER.index(first.source), first.rank)
