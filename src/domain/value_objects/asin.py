from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ASIN_BODY = re.compile(r"^[A-Z0-9]{10}$")
_ASIN_IN_URL = re.compile(
    r"/(?:dp|gp/product|gp/aw/d|product)/([A-Za-z0-9]{10})(?:[/?#]|$)", re.IGNORECASE
)


@dataclass(frozen=True)
class Asin:
    value: str

    @classmethod
    def parse(cls, raw: object) -> Asin | None:
        if raw is None:
            return None

        text = unicodedata.normalize("NFKC", str(raw)).strip()
        if not text:
            return None

        if text.lower().startswith("http"):
            return cls._from_url(text)

        candidate = text.upper()
        return cls(candidate) if _ASIN_BODY.match(candidate) else None

    @classmethod
    def _from_url(cls, url: str) -> Asin | None:
        matched = _ASIN_IN_URL.search(url)
        return cls(matched.group(1).upper()) if matched else None

    @property
    def amazon_url(self) -> str:
        return f"https://www.amazon.co.jp/dp/{self.value}"

    def __str__(self) -> str:
        return self.value
