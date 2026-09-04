from __future__ import annotations

from src.domain.entities.rival_candidate import (
    SOURCE_ORDER,
    RivalCandidate,
    RivalPlacement,
)
from src.domain.value_objects.asin import Asin

DEFAULT_LIMIT_PER_SOURCE = 3


def _to_rank(raw: object) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        rank = int(str(raw).strip())
    except ValueError:
        return None
    return rank if rank > 0 else None


def merge_candidates(
    sources: dict[str, list[tuple[str, str, object]]],
    exclude: Asin | None = None,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
) -> list[RivalCandidate]:
    titles: dict[str, str] = {}
    placements: dict[str, list[RivalPlacement]] = {}
    order: list[str] = []

    for source in SOURCE_ORDER:
        taken = 0
        for raw_asin, title, raw_rank in sources.get(source) or []:
            if taken >= limit_per_source:
                break

            asin = Asin.parse(raw_asin)
            rank = _to_rank(raw_rank)
            if asin is None or rank is None:
                continue
            if exclude is not None and asin.value == exclude.value:
                continue

            taken += 1
            if asin.value not in placements:
                placements[asin.value] = []
                titles[asin.value] = title
                order.append(asin.value)
            placements[asin.value].append(RivalPlacement(source=source, rank=rank))

    candidates = [
        RivalCandidate(
            asin=Asin.parse(value),
            title=titles[value],
            placements=tuple(placements[value]),
        )
        for value in order
    ]
    return sorted(candidates, key=lambda candidate: candidate.sort_key())


def rival_row_numbers(base_row: int, count: int) -> list[int]:
    return [base_row + offset + 1 for offset in range(count)]


def plan_rival_rows(base_row: int, count: int) -> dict[str, int] | None:
    if count <= 0:
        return None
    return {"start_row": base_row + 1, "count": count}


def build_rival_updates(
    candidates: list[RivalCandidate],
    base_row: int,
    asin_column: int,
    rank_column: int,
) -> dict[int, dict[int, object]]:
    rows = rival_row_numbers(base_row, len(candidates))
    return {
        row_number: {
            asin_column: candidate.asin.value,
            rank_column: candidate.rank_label(),
        }
        for row_number, candidate in zip(rows, candidates)
    }


def plan_column_insert(codes: list[str], after_code: str, new_code: str) -> int | None:
    stripped = [str(code).strip() for code in codes]
    if new_code in stripped:
        return None
    if after_code not in stripped:
        raise ValueError(f"基準の列コード {after_code} がありません")
    return stripped.index(after_code) + 1
