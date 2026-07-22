"""Shared data models for Neerslag Radar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One normalized precipitation forecast interval."""

    forecast_time: datetime
    interval_minutes: int
    precipitation_mm: float
    intensity_mm_h: float
    probability: float | None = None
    uncertainty_mm: float | None = None
    precipitation_type: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a compact Home Assistant attribute representation."""
        result: dict[str, Any] = {
            "datetime": self.forecast_time.isoformat(),
            "interval_minutes": self.interval_minutes,
            "precipitation": round(self.precipitation_mm, 3),
            "precipitation_intensity": round(self.intensity_mm_h, 3),
        }
        if self.probability is not None:
            result["probability"] = round(self.probability, 1)
        if self.uncertainty_mm is not None:
            result["uncertainty"] = round(self.uncertainty_mm, 3)
        if self.precipitation_type is not None:
            result["precipitation_type"] = self.precipitation_type
        return result


@dataclass(frozen=True, slots=True)
class ForecastData:
    """Normalized response from a provider."""

    points: tuple[ForecastPoint, ...]
    source_updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_precipitation_mm(self) -> float:
        """Return the total amount over all available points."""
        return sum(point.precipitation_mm for point in self.points)
