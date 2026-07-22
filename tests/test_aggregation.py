"""Tests for the calculated Global forecast."""

from datetime import UTC, datetime

import pytest

from custom_components.neerslag_radar.aggregation import aggregate_global_forecast
from custom_components.neerslag_radar.models import ForecastData, ForecastPoint


def _point(
    forecast_time: datetime, interval_minutes: int, amount: float, source: str
) -> ForecastPoint:
    return ForecastPoint(
        forecast_time=forecast_time,
        interval_minutes=interval_minutes,
        precipitation_mm=amount,
        intensity_mm_h=amount * 60 / interval_minutes,
        source=source,
    )


def test_global_uses_highest_normalized_provider_value() -> None:
    start = datetime(2026, 7, 22, 17, 0, tzinfo=UTC)
    result = aggregate_global_forecast(
        {
            "buienradar": ForecastData((_point(start, 5, 0.0, "Buienradar"),)),
            "buienalarm": ForecastData((_point(start, 5, 0.0, "Buienalarm"),)),
            "knmi": ForecastData((_point(start, 5, 1.2, "KNMI"),)),
            "open_meteo": ForecastData((_point(start, 15, 0.4, "Open-Meteo"),)),
        },
        now=start,
    )

    point = result.points[0]
    assert point.precipitation_mm == pytest.approx(1.2)
    assert point.source == "knmi"
    assert point.provider_values == {
        "buienradar": pytest.approx(0.0),
        "buienalarm": pytest.approx(0.0),
        "knmi": pytest.approx(1.2),
        "open_meteo": pytest.approx(0.4 / 3),
    }
    assert point.as_dict()["selected_provider"] == "knmi"


def test_global_distributes_quarter_hour_amount_over_five_minute_slots() -> None:
    start = datetime(2026, 7, 22, 17, 0, tzinfo=UTC)
    result = aggregate_global_forecast(
        {"open_meteo": ForecastData((_point(start, 15, 0.45, "Open-Meteo"),))},
        now=start,
    )

    assert len(result.points) == 3
    assert [point.precipitation_mm for point in result.points] == pytest.approx(
        [0.15, 0.15, 0.15]
    )
    assert result.total_precipitation_mm == pytest.approx(0.45)


def test_global_starts_at_next_five_minute_boundary() -> None:
    point_start = datetime(2026, 7, 22, 17, 5, tzinfo=UTC)
    result = aggregate_global_forecast(
        {"knmi": ForecastData((_point(point_start, 5, 0.2, "KNMI"),))},
        now=datetime(2026, 7, 22, 17, 2, 30, tzinfo=UTC),
    )

    assert result.points[0].forecast_time == point_start


def test_global_returns_empty_forecast_without_provider_coverage() -> None:
    result = aggregate_global_forecast(
        {}, now=datetime(2026, 7, 22, 17, 0, tzinfo=UTC)
    )

    assert result.points == ()
    assert result.metadata["providers"] == []
