from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

# 成形品は実測がばらつく。仕入元と出品側で 0.3mm ずれても同じ型のことが多い
ABSOLUTE_TOLERANCE_MM = 0.3
RELATIVE_TOLERANCE = 0.05

_LABELS = "幅|巾|横|縦|高さ|高|長さ|長|奥行|厚さ|厚|直径|径|穴径|内径|外径|宽|寬|高|长|厚|孔径|吊孔直径"
_UNITS = {"mm": 1.0, "MM": 1.0, "ミリ": 1.0, "毫米": 1.0, "cm": 10.0, "CM": 10.0, "センチ": 10.0, "厘米": 10.0}
_UNIT_PATTERN = "|".join(_UNITS)

# 「幅8mm」「高约16毫米」「穴径：2.5mm」
LABELED = re.compile(rf"({_LABELS})\s*[:：]?\s*(?:约|約)?\s*(\d+(?:\.\d+)?)\s*({_UNIT_PATTERN})")
# 「20*10*3mm」
PRODUCT = re.compile(rf"(\d+(?:\.\d+)?(?:\s*[*xX×]\s*\d+(?:\.\d+)?)+)\s*({_UNIT_PATTERN})")
COUNT = re.compile(r"(\d+)\s*(?:個|个|枚|本|pcs|PCS|セット)")


class Match(Enum):
    SAME = "same"
    PARTIAL = "partial"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Dimension:
    label: str
    millimeters: float


@dataclass(frozen=True)
class Comparison:
    verdict: Match
    matched: list[tuple[float, float]]
    unmatched: list[float]


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def extract_dimensions(text: str) -> list[Dimension]:
    normalized = _normalize(text)
    found: list[Dimension] = []

    for raw, unit in PRODUCT.findall(normalized):
        scale = _UNITS[unit]
        found.extend(
            Dimension("", float(part) * scale) for part in re.split(r"[*xX×]", raw) if part.strip()
        )

    for label, value, unit in LABELED.findall(normalized):
        found.append(Dimension(label, float(value) * _UNITS[unit]))

    return found


def pack_counts(text: str) -> list[int]:
    return [int(n) for n in COUNT.findall(_normalize(text))]


def _within_tolerance(left: float, right: float) -> bool:
    allowed = max(ABSOLUTE_TOLERANCE_MM, max(left, right) * RELATIVE_TOLERANCE)
    return abs(left - right) <= allowed


def compare(amazon: list[Dimension], supplier: list[Dimension]) -> Comparison:
    if not amazon or not supplier:
        return Comparison(Match.UNKNOWN, [], [])

    # ラベルは日本語と中国語で呼び方が違うので、値だけで突き合わせる
    remaining = [d.millimeters for d in supplier]
    matched: list[tuple[float, float]] = []
    unmatched: list[float] = []

    for dimension in amazon:
        hit = next((v for v in remaining if _within_tolerance(dimension.millimeters, v)), None)
        if hit is None:
            unmatched.append(dimension.millimeters)
            continue
        remaining.remove(hit)
        matched.append((dimension.millimeters, hit))

    if not matched:
        return Comparison(Match.DIFFERENT, matched, unmatched)
    if unmatched:
        return Comparison(Match.PARTIAL if matched else Match.DIFFERENT, matched, unmatched)
    return Comparison(Match.SAME, matched, unmatched)
