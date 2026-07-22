"""Tests for forecast slot names."""

from datetime import UTC, datetime

from custom_components.neerslag_radar.models import (
    ForecastPoint,
    format_forecast_interval,
)


def _point(forecast_time: datetime, interval_minutes: int) -> ForecastPoint:
    return ForecastPoint(
        forecast_time=forecast_time,
        interval_minutes=interval_minutes,
        precipitation_mm=0,
        intensity_mm_h=0,
    )


def test_formats_five_minute_interval_in_home_assistant_timezone() -> None:
    """The visible name uses the local start and end time."""
    point = _point(datetime(2026, 7, 22, 15, 50, tzinfo=UTC), 5)

    assert format_forecast_interval(point, "Europe/Amsterdam") == "17:50–17:55"


def test_formats_provider_interval_duration() -> None:
    """The visible name reflects the provider's actual interval duration."""
    point = _point(datetime(2026, 7, 22, 15, 45, tzinfo=UTC), 15)

    assert format_forecast_interval(point, "Europe/Amsterdam") == "17:45–18:00"


def test_formats_interval_across_midnight() -> None:
    """An interval crossing midnight remains concise and unambiguous."""
    point = _point(datetime(2026, 7, 22, 21, 55, tzinfo=UTC), 5)

    assert format_forecast_interval(point, "Europe/Amsterdam") == "23:55–00:00"
