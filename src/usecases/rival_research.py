from __future__ import annotations

from src.domain.entities.rival_candidate import (
    SOURCE_ORDER,
    RivalCandidate,
    RivalPlacement,
)
import unicodedata

from src.domain.value_objects.asin import Asin
from src.domain.value_objects.discovery_criteria import EXCLUDED_BRANDS

DEFAULT_LIMIT_PER_SOURCE = 3


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def is_excluded_brand(title: str) -> bool:
    # 有名ブランドは同じ棚に並んでも中国輸入の競合にならないので候補にしない
    lowered = _normalize(title)
    return any(_normalize(brand) in lowered for brand in EXCLUDED_BRANDS)


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
    adopted: set[str] = set()

    # 採用は経路ごとの上位 limit_per_source 件で決めるが、順位ラベルには
    # 採用に使わなかった経路の順位も載せる（同じ商品が何経路に出ているかが要る）
    for source in SOURCE_ORDER:
        rank_in_source = 0
        for raw_asin, title, raw_rank in sources.get(source) or []:
            asin = Asin.parse(raw_asin)
            rank = _to_rank(raw_rank)
            if asin is None or rank is None:
                continue
            if exclude is not None and asin.value == exclude.value:
                continue
            if is_excluded_brand(title):
                continue

            rank_in_source += 1
            if asin.value not in placements:
                placements[asin.value] = []
                titles[asin.value] = title
                order.append(asin.value)
            placements[asin.value].append(RivalPlacement(source=source, rank=rank))

            if rank_in_source <= limit_per_source:
                adopted.add(asin.value)

    candidates = [
        RivalCandidate(
            asin=Asin.parse(value),
            title=titles[value],
            placements=tuple(placements[value]),
        )
        for value in order
        if value in adopted
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


def is_raw_collect_output(payload: dict) -> bool:
    # collect は ranking_url を付けて返す。絞り込まずにそのまま write へ渡すと
    # 同一判定を飛ばして無関係な商品まで行になるので、これで見分ける
    return "ranking_url" in payload


def prunable_rows(
    values: list[list],
    asin_column: int,
    rank_column: int,
    title_column: int,
    header_rows: int,
) -> list[int]:
    # 順位が入っている行だけがライバル調査で足した行。自社の行を消さないための目印になる
    rows: list[int] = []
    for offset, row in enumerate(values[header_rows:]):
        def read(index: int) -> str:
            return str(row[index]).strip() if index < len(row) else ""

        if not read(rank_column) or Asin.parse(read(asin_column)) is None:
            continue
        if is_excluded_brand(read(title_column)):
            rows.append(header_rows + offset + 1)
    return rows
