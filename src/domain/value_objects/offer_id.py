from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = re.compile(r"^\d+$")
_OFFER_IN_URL = re.compile(r"/offer/(\d+)\.html")


@dataclass(frozen=True)
class OfferId:
    value: str

    @classmethod
    def parse(cls, raw: object) -> OfferId | None:
        if raw is None:
            return None

        text = str(raw).strip()
        if not text:
            return None

        matched = _OFFER_IN_URL.search(text)
        if matched:
            return cls(matched.group(1))

        return cls(text) if _DIGITS.match(text) else None

    @property
    def detail_url(self) -> str:
        return f"https://detail.1688.com/offer/{self.value}.html"

    def __str__(self) -> str:
        return self.value
