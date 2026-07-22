"""Tests for the Buienradar parser."""

from datetime import UTC, datetime

import pytest

from custom_components.neerslag_radar.providers.base import ProviderDataError
from custom_components.neerslag_radar.providers.buienradar import (
    intensity_from_code,
    parse_buienradar,
)


def test_parse_buienradar_and_convert_codes() -> None:
    now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    result = parse_buienradar("\ufeff000|12:05\r\n116|12:10\r\n", now)

    assert len(result.points) == 2
    assert result.points[0].precipitation_mm == 0
    assert result.points[1].intensity_mm_h == pytest.approx(intensity_from_code(116))
    assert result.points[1].precipitation_mm == pytest.approx(intensity_from_code(116) / 12)


def test_parse_buienradar_midnight_rollover() -> None:
    now = datetime(2026, 7, 22, 21, 50, tzinfo=UTC)
    result = parse_buienradar("077|23:55\n087|00:00\n", now)

    assert result.points[1].forecast_time > result.points[0].forecast_time
    assert (result.points[1].forecast_time - result.points[0].forecast_time).seconds == 300


def test_parse_buienradar_rejects_duplicate_time() -> None:
    now = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
    with pytest.raises(ProviderDataError):
        parse_buienradar("077|12:05\n087|12:05\n", now)
