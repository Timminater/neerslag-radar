"""Tests for the experimental Buienalarm parser."""

from datetime import UTC, datetime

import pytest

from custom_components.neerslag_radar.providers.base import ProviderDataError
from custom_components.neerslag_radar.providers.buienalarm import parse_buienalarm
from custom_components.neerslag_radar.providers.buienradar import intensity_from_code


def test_parse_current_buienalarm_values() -> None:
    now = datetime(2026, 7, 22, 13, 10, tzinfo=UTC)
    payload = {
        "data": [
            {
                "precipitationrate": 1.2,
                "precipitationtype": "rain",
                "time": "2026-07-22T13:10:00Z",
                "timestamp": 1784725800,
            },
            {
                "precipitationrate": 2.4,
                "precipitationtype": "rain",
                "time": "2026-07-22T13:15:00Z",
                "timestamp": 1784726100,
            },
        ],
        "nowcastmessage": {"nl": "Regen verwacht"},
    }

    result = parse_buienalarm(payload, now)

    assert len(result.points) == 2
    assert result.points[0].interval_minutes == 5
    assert result.points[0].intensity_mm_h == pytest.approx(1.2)
    assert result.points[0].precipitation_mm == pytest.approx(0.1)
    assert result.points[0].precipitation_type == "rain"
    assert result.metadata["api_version"] == "v4"


def test_parse_buienalarm_encoded_values() -> None:
    now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    payload = {
        "success": True,
        "start": int(now.timestamp()),
        "delta": 300,
        "precip": [116, 0, 87],
        "unexpected": "ignored",
    }

    result = parse_buienalarm(payload, now)

    assert len(result.points) == 3
    assert result.points[0].intensity_mm_h == pytest.approx(intensity_from_code(116))
    assert result.points[0].precipitation_mm == pytest.approx(intensity_from_code(116) / 12)
    assert result.points[1].precipitation_mm == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "start": 1, "delta": 300, "precip": [0]},
        {"success": True, "delta": 300, "precip": [0]},
        {"success": True, "start": 1, "delta": 0, "precip": [0]},
        {"success": True, "start": 1, "delta": 300, "precip": [256]},
        {"data": []},
        {"data": [{"time": "2026-07-22T10:00:00Z", "precipitationrate": 1.0}]},
        {
            "data": [
                {"time": "2026-07-22T10:00:00Z", "precipitationrate": -1.0},
                {"time": "2026-07-22T10:05:00Z", "precipitationrate": 1.0},
            ]
        },
    ],
)
def test_parse_buienalarm_rejects_invalid_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ProviderDataError):
        parse_buienalarm(payload, datetime(2026, 7, 22, 10, 0, tzinfo=UTC))


def test_parse_buienalarm_rejects_stale_forecast() -> None:
    now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    payload = {
        "success": True,
        "start": int(datetime(2026, 7, 22, 6, 0, tzinfo=UTC).timestamp()),
        "delta": 300,
        "precip": [0] * 25,
    }
    with pytest.raises(ProviderDataError):
        parse_buienalarm(payload, now)
