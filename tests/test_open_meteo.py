"""Tests for the Open-Meteo parser."""

from datetime import UTC, datetime

import pytest

from custom_components.neerslag_radar.providers.base import ProviderDataError
from custom_components.neerslag_radar.providers.open_meteo import parse_open_meteo


def test_parse_open_meteo_interval_amounts() -> None:
    now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    payload = {
        "minutely_15_units": {"precipitation": "mm"},
        "minutely_15": {
            "time": ["2026-07-22T10:00", "2026-07-22T10:15", "2026-07-22T10:30"],
            "precipitation": [9.0, 0.5, 1.25],
        },
    }

    result = parse_open_meteo(payload, now)

    assert len(result.points) == 2
    assert result.points[0].precipitation_mm == 0.5
    assert result.points[0].intensity_mm_h == 2.0


def test_parse_open_meteo_rejects_mismatched_arrays() -> None:
    payload = {
        "minutely_15": {
            "time": ["2026-07-22T10:15"],
            "precipitation": [0.5, 1.0],
        }
    }
    with pytest.raises(ProviderDataError):
        parse_open_meteo(payload, datetime(2026, 7, 22, 10, 0, tzinfo=UTC))


def test_parse_open_meteo_rejects_inches() -> None:
    payload = {
        "minutely_15_units": {"precipitation": "inch"},
        "minutely_15": {"time": ["2026-07-22T10:15"], "precipitation": [0.5]},
    }
    with pytest.raises(ProviderDataError):
        parse_open_meteo(payload, datetime(2026, 7, 22, 10, 0, tzinfo=UTC))
