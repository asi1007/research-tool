from __future__ import annotations

from dataclasses import dataclass

DECIDED_BY_CLAUDE = "claude"
DECIDED_BY_HUMAN = "human"


@dataclass(frozen=True)
class SeasonalVerdict:
    seasonal: bool
    decided_by: str


class SeasonalVerdicts:
    def __init__(self, verdicts: dict[str, SeasonalVerdict] | None = None) -> None:
        self._verdicts: dict[str, SeasonalVerdict] = dict(verdicts or {})

    def is_seasonal(self, asin: str) -> bool | None:
        verdict = self._verdicts.get(asin)
        return None if verdict is None else verdict.seasonal

    def unjudged(self, asins: list[str]) -> list[str]:
        return [asin for asin in asins if asin not in self._verdicts]

    def record_claude(self, asin: str, seasonal: bool) -> None:
        current = self._verdicts.get(asin)
        if current is not None and current.decided_by == DECIDED_BY_HUMAN:
            return
        self._verdicts[asin] = SeasonalVerdict(seasonal, DECIDED_BY_CLAUDE)

    def record_human(self, asin: str, seasonal: bool) -> None:
        self._verdicts[asin] = SeasonalVerdict(seasonal, DECIDED_BY_HUMAN)

    def items(self) -> list[tuple[str, SeasonalVerdict]]:
        return sorted(self._verdicts.items())
