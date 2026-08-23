from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductSize:
    length_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0

    @property
    def volumetric_weight_kg(self) -> float:
        return (self.length_mm / 10) * (self.width_mm / 10) * (self.height_mm / 10) / 5000

    @property
    def is_empty(self) -> bool:
        return not (self.length_mm and self.width_mm and self.height_mm)
