"""Shared data models for Neerslag Radar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


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
    provider_values: dict[str, float] | None = None

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
        if self.source is not None:
            result["source"] = self.source
        if self.provider_values is not None:
            result["selected_provider"] = self.source
            result["provider_values"] = {
                provider: round(value, 3)
                for provider, value in self.provider_values.items()
            }
        return result


def format_forecast_interval(point: ForecastPoint, time_zone: str) -> str:
    """Format a forecast point as a local start and end time."""
    start = point.forecast_time.astimezone(ZoneInfo(time_zone))
    end = start + timedelta(minutes=point.interval_minutes)
    return f"{start:%H:%M}–{end:%H:%M}"


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
