from __future__ import annotations

from dataclasses import dataclass

from src.domain.value_objects.offer_id import OfferId


@dataclass(frozen=True)
class SupplierCandidate:
    offer_id: OfferId
    title: str
    company: str
    province: str
    local_price: float | None
    quantity: int

    @property
    def url(self) -> str:
        return self.offer_id.detail_url
