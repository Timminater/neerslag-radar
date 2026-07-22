"""Normalize and aggregate forecasts for the Global provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import ForecastData, ForecastPoint

GLOBAL_INTERVAL_MINUTES = 5
GLOBAL_SLOT_COUNT = 36


def aggregate_global_forecast(
    provider_data: dict[str, ForecastData], now: datetime | None = None
) -> ForecastData:
    """Return the highest provider amount for each canonical five-minute slot."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    slot_start = current.replace(second=0, microsecond=0)
    remainder = slot_start.minute % GLOBAL_INTERVAL_MINUTES
    if remainder or current.second or current.microsecond:
        slot_start += timedelta(minutes=GLOBAL_INTERVAL_MINUTES - remainder)

    aggregated: list[ForecastPoint | None] = []
    interval = timedelta(minutes=GLOBAL_INTERVAL_MINUTES)
    for slot_index in range(GLOBAL_SLOT_COUNT):
        start = slot_start + slot_index * interval
        end = start + interval
        values: dict[str, float] = {}

        for provider, data in provider_data.items():
            amount = 0.0
            covered = False
            for point in data.points:
                point_start = point.forecast_time.astimezone(UTC)
                point_interval = timedelta(minutes=point.interval_minutes)
                point_end = point_start + point_interval
                overlap = min(end, point_end) - max(start, point_start)
                if overlap <= timedelta(0):
                    continue
                covered = True
                amount += point.precipitation_mm * (
                    overlap.total_seconds() / point_interval.total_seconds()
                )
            if covered:
                values[provider] = max(0.0, amount)

        if not values:
            aggregated.append(None)
            continue
        selected_provider, selected_amount = max(
            values.items(), key=lambda item: (item[1], item[0])
        )
        aggregated.append(
            ForecastPoint(
                forecast_time=start,
                interval_minutes=GLOBAL_INTERVAL_MINUTES,
                precipitation_mm=selected_amount,
                intensity_mm_h=selected_amount * 60 / GLOBAL_INTERVAL_MINUTES,
                source=selected_provider,
                provider_values=values,
            )
        )

    while aggregated and aggregated[-1] is None:
        aggregated.pop()
    points = tuple(point for point in aggregated if point is not None)
    return ForecastData(
        points,
        metadata={
            "aggregation": "maximum",
            "interval_minutes": GLOBAL_INTERVAL_MINUTES,
            "providers": sorted(provider_data),
        },
    )
