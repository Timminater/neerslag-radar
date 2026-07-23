"""Entity contracts for provider and Global forecast overview sensors."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("homeassistant") is None,
    reason="Home Assistant is required for entity tests",
)


def _forecast():
    from custom_components.neerslag_radar.models import ForecastData, ForecastPoint

    start = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    return ForecastData(
        points=(
            ForecastPoint(
                forecast_time=start,
                interval_minutes=5,
                precipitation_mm=0.2,
                intensity_mm_h=2.4,
            ),
            ForecastPoint(
                forecast_time=start + timedelta(minutes=5),
                interval_minutes=5,
                precipitation_mm=0.1,
                intensity_mm_h=1.2,
            ),
        )
    )


def _coordinator(data):
    return SimpleNamespace(data=data, last_update_success=True)


def test_provider_overview_exposes_card_location_contract() -> None:
    """Provider totals expose stable location metadata without changing the forecast."""
    from custom_components.neerslag_radar.const import ProviderType
    from custom_components.neerslag_radar.sensor import PrecipitationOverviewSensor

    entry = SimpleNamespace(entry_id="location-opaque-id", title="Thuis")
    sensor = PrecipitationOverviewSensor(
        entry, "buienradar-subentry", _coordinator(_forecast()), ProviderType.BUIENRADAR
    )

    assert sensor.unique_id == "location-opaque-id_buienradar-subentry_total"
    assert sensor.extra_state_attributes == {
        "provider": "buienradar",
        "location_id": "location-opaque-id",
        "location_name": "Thuis",
        "forecast_schema_version": 1,
        "forecast": [
            {
                "datetime": "2026-07-23T10:00:00+00:00",
                "interval_minutes": 5,
                "precipitation": 0.2,
                "precipitation_intensity": 2.4,
            },
            {
                "datetime": "2026-07-23T10:05:00+00:00",
                "interval_minutes": 5,
                "precipitation": 0.1,
                "precipitation_intensity": 1.2,
            },
        ],
        "forecast_start": "2026-07-23T10:00:00+00:00",
        "forecast_end": "2026-07-23T10:05:00+00:00",
        "point_count": 2,
    }


def test_global_overview_is_excluded_from_card_location_contract() -> None:
    """Global retains its forecast contract but has no provider-location metadata."""
    from custom_components.neerslag_radar.sensor import GlobalOverviewSensor

    entry = SimpleNamespace(entry_id="location-opaque-id", title="Thuis")
    sensor = GlobalOverviewSensor(entry, _coordinator(_forecast()))

    assert sensor.unique_id == "location-opaque-id_global_total"
    attributes = sensor.extra_state_attributes
    assert attributes["provider"] == "global"
    assert attributes["forecast_start"] == "2026-07-23T10:00:00+00:00"
    assert attributes["forecast_end"] == "2026-07-23T10:05:00+00:00"
    assert attributes["point_count"] == 2
    assert len(attributes["forecast"]) == 2
    assert not {
        "location_id",
        "location_name",
        "forecast_schema_version",
    }.intersection(attributes)
