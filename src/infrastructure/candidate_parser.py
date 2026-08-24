from __future__ import annotations

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId

DEFAULT_LIMIT = 3


def _to_price(raw: object) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def _to_text(raw: object) -> str:
    return "" if raw is None else str(raw).strip()


def parse_candidates(
    raw_items: list[dict], limit: int = DEFAULT_LIMIT
) -> list[SupplierCandidate]:
    candidates: list[SupplierCandidate] = []
    seen: set[str] = set()

    for item in raw_items:
        if len(candidates) >= limit:
            break

        offer_id = OfferId.parse(item.get("offerId"))
        if offer_id is None or offer_id.value in seen:
            continue

        seen.add(offer_id.value)
        candidates.append(
            SupplierCandidate(
                offer_id=offer_id,
                title=_to_text(item.get("title")),
                company=_to_text(item.get("company")),
                province=_to_text(item.get("province")),
                local_price=_to_price(item.get("price")),
            )
        )

    return candidates
