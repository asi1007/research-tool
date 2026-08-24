from __future__ import annotations

import math

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.domain.value_objects.offer_id import OfferId

DEFAULT_LIMIT = 3


def _to_price(raw: object) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        price = float(str(raw).strip())
        if not math.isfinite(price):
            return None
        return price
    except ValueError:
        return None


def _to_text(raw: object) -> str:
    return "" if raw is None else str(raw).strip()


def _to_quantity(raw: object) -> int:
    if raw is None or isinstance(raw, bool):
        return 1
    if isinstance(raw, int):
        return raw if raw > 0 else 1
    if isinstance(raw, str):
        text = raw.strip()
        if not text.isdigit():
            return 1
        value = int(text)
        return value if value > 0 else 1
    return 1


def parse_candidates(
    raw_items: list[dict], limit: int = DEFAULT_LIMIT
) -> list[SupplierCandidate]:
    candidates: list[SupplierCandidate] = []
    seen: set[str] = set()

    for item in raw_items:
        if len(candidates) >= limit:
            break

        if not isinstance(item, dict):
            continue

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
                quantity=_to_quantity(item.get("quantity")),
            )
        )

    return candidates
