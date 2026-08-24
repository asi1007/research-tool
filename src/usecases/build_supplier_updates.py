from __future__ import annotations

from dataclasses import dataclass

from src.domain.entities.supplier_candidate import SupplierCandidate
from src.infrastructure.column_codes import ColumnCodes
from src.infrastructure.sheet_repository import column_letter

CURRENCY = "CHY"
CNY_TO_JPY_RATE = 24


@dataclass(frozen=True)
class CandidateSlot:
    link: str
    price: str
    local_price: str
    currency: str | None


SLOTS = (
    CandidateSlot("LINK_LOWEST", "PRICE_LOWEST", "LOCALPRICE_LOWEST", None),
    CandidateSlot(
        "LINK_BUY_OTHER1", "PRICE_BUY_OTHER1", "LOCALPRICE_BUY_OTHER1", "CURRENCY_BUY_OTHER1"
    ),
    CandidateSlot(
        "LINK_BUY_OTHER2", "PRICE_BUY_OTHER2", "LOCALPRICE_BUY_OTHER2", "CURRENCY_BUY_OTHER2"
    ),
)


def _put(updates: dict[int, object], index: int | None, value: object) -> None:
    if index is not None:
        updates[index] = value


def build_updates(
    row_number: int, candidates: list[SupplierCandidate], codes: ColumnCodes
) -> dict[int, object]:
    updates: dict[int, object] = {}

    for slot, candidate in zip(SLOTS, candidates):
        _put(updates, codes.index_of(slot.link), candidate.url)

        if slot.currency:
            _put(updates, codes.index_of(slot.currency), CURRENCY)

        if candidate.local_price is None:
            continue

        local_index = codes.index_of(slot.local_price)
        _put(updates, local_index, candidate.local_price)

        if local_index is not None:
            formula = f"={column_letter(local_index)}{row_number}*{CNY_TO_JPY_RATE}"
            _put(updates, codes.index_of(slot.price), formula)

    return updates
