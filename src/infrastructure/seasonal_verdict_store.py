from __future__ import annotations

import json
from pathlib import Path

from src.domain.value_objects.seasonal_verdicts import SeasonalVerdict, SeasonalVerdicts


class JsonSeasonalVerdictStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> SeasonalVerdicts:
        if not self.path.exists():
            return SeasonalVerdicts()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return SeasonalVerdicts(
            {
                asin: SeasonalVerdict(bool(entry["seasonal"]), str(entry["decided_by"]))
                for asin, entry in raw.items()
            }
        )

    def save(self, verdicts: SeasonalVerdicts) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            asin: {"seasonal": verdict.seasonal, "decided_by": verdict.decided_by}
            for asin, verdict in verdicts.items()
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
