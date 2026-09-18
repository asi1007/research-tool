from __future__ import annotations

import json
from pathlib import Path


class SupplierSkips:
    """画像検索で外れた・1688に同款が無いと分かったASIN。次の自動実行で拾い直さないために残す。"""

    def __init__(self, reasons: dict[str, str] | None = None) -> None:
        self._reasons = dict(reasons or {})

    @classmethod
    def load(cls, path: Path) -> SupplierSkips:
        if not path.exists():
            return cls()
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._reasons, ensure_ascii=False, indent=1), encoding="utf-8")

    def contains(self, asin: str) -> bool:
        return asin in self._reasons

    def add(self, asin: str, reason: str) -> None:
        self._reasons[asin] = reason

    def __len__(self) -> int:
        return len(self._reasons)
