"""Experimental Buienalarm precipitation forecast provider."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientError, ClientResponseError

from ..models import ForecastData, ForecastPoint
from .base import PrecipitationProvider, ProviderConnectionError, ProviderDataError
from .buienradar import intensity_from_code
from .http import async_get

URL = "https://imn-rust-lb.infoplaza.io/v4/nowcast/ba/timeseries/{latitude}/{longitude}"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.buienalarm.nl",
    "Referer": "https://www.buienalarm.nl/",
    "User-Agent": (
        "HomeAssistant-NeerslagRadar/0.1.0 "
        "(+https://github.com/Timminater/neerslag-radar)"
    ),
}


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as err:
            raise ProviderDataError("Invalid Buienalarm timestamp") from err
        return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as err:
        raise ProviderDataError("Invalid Buienalarm timestamp") from err
    if numeric > 10_000_000_000:
        numeric /= 1000
    return datetime.fromtimestamp(numeric, UTC)


def parse_buienalarm(payload: dict[str, Any], now: datetime | None = None) -> ForecastData:
    """Parse known Buienalarm response variants."""
    if payload.get("success") is False:
        raise ProviderDataError("Buienalarm reported an unsuccessful response")
    if isinstance(payload.get("data"), list):
        return _parse_current_buienalarm(payload, now)

    return _parse_legacy_buienalarm(payload, now)


def _parse_current_buienalarm(
    payload: dict[str, Any], now: datetime | None = None
) -> ForecastData:
    """Parse the current undocumented v4 timeseries response."""
    records = payload["data"]
    if not records:
        raise ProviderDataError("Buienalarm response has no forecast points")

    parsed: list[tuple[datetime, float, str | None]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ProviderDataError("Invalid Buienalarm forecast point")
        timestamp = record.get("time", record.get("timestamp"))
        if timestamp is None:
            raise ProviderDataError("Buienalarm forecast point has no timestamp")
        try:
            raw_intensity = record["precipitationrate"]
            if isinstance(raw_intensity, bool):
                raise ValueError
            intensity = float(raw_intensity)
        except (KeyError, TypeError, ValueError) as err:
            raise ProviderDataError("Invalid Buienalarm precipitation rate") from err
        if not math.isfinite(intensity) or intensity < 0:
            raise ProviderDataError("Invalid Buienalarm precipitation rate")
        precipitation_type = record.get("precipitationtype")
        parsed.append(
            (
                _timestamp(timestamp),
                intensity,
                precipitation_type if isinstance(precipitation_type, str) else None,
            )
        )

    parsed.sort(key=lambda item: item[0])
    intervals: list[int] = []
    for index in range(len(parsed) - 1):
        seconds = (parsed[index + 1][0] - parsed[index][0]).total_seconds()
        if seconds < 60 or seconds > 3600 or seconds % 60:
            raise ProviderDataError("Buienalarm returned an unsupported interval")
        intervals.append(int(seconds // 60))
    if not intervals:
        raise ProviderDataError("Buienalarm returned too few forecast points")
    intervals.append(intervals[-1])

    current = (now or datetime.now(UTC)).astimezone(UTC)
    points = tuple(
        ForecastPoint(
            forecast_time=forecast_time,
            interval_minutes=interval_minutes,
            precipitation_mm=intensity * interval_minutes / 60,
            intensity_mm_h=intensity,
            source="Buienalarm",
            precipitation_type=precipitation_type,
        )
        for (forecast_time, intensity, precipitation_type), interval_minutes in zip(
            parsed, intervals, strict=True
        )
        if current - timedelta(minutes=interval_minutes)
        < forecast_time
        <= current + timedelta(hours=3)
    )
    if not points or points[-1].forecast_time <= current:
        raise ProviderDataError("Buienalarm returned only stale forecast points")
    return ForecastData(points, metadata={"experimental": True, "api_version": "v4"})


def _parse_legacy_buienalarm(
    payload: dict[str, Any], now: datetime | None = None
) -> ForecastData:
    """Parse the former v3.4 response for fixture and transition compatibility."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    precipitation = data.get("precip") or data.get("precipitation")
    if not isinstance(precipitation, list) or not precipitation:
        raise ProviderDataError("Buienalarm response has no precipitation array")

    raw_interval = data.get("delta", data.get("interval", 300))
    try:
        interval_seconds = int(raw_interval)
    except (TypeError, ValueError) as err:
        raise ProviderDataError("Invalid Buienalarm interval") from err
    if interval_seconds < 60:
        interval_seconds *= 60
    if interval_seconds <= 0 or interval_seconds > 3600:
        raise ProviderDataError("Buienalarm interval is outside the supported range")
    interval_minutes = max(1, interval_seconds // 60)
    start_value = data.get("start") or data.get("start_time")
    if start_value is None:
        raise ProviderDataError("Buienalarm response has no start timestamp")
    start = _timestamp(start_value)
    timestamps = data.get("time") or data.get("times")

    points: list[ForecastPoint] = []
    for index, raw_value in enumerate(precipitation[: 180 // interval_minutes]):
        try:
            if isinstance(raw_value, bool):
                raise ValueError
            code = int(raw_value)
        except (TypeError, ValueError) as err:
            raise ProviderDataError("Invalid Buienalarm precipitation value") from err
        if code < 0 or code > 255:
            raise ProviderDataError("Buienalarm precipitation code is outside 0..255")
        intensity = intensity_from_code(code)
        if not math.isfinite(intensity):
            raise ProviderDataError("Invalid Buienalarm precipitation intensity")
        forecast_time = (
            _timestamp(timestamps[index])
            if isinstance(timestamps, list) and index < len(timestamps)
            else start + timedelta(seconds=index * interval_seconds)
        )
        points.append(
            ForecastPoint(
                forecast_time=forecast_time.astimezone(UTC),
                interval_minutes=interval_minutes,
                precipitation_mm=intensity * interval_minutes / 60,
                intensity_mm_h=intensity,
                source="Buienalarm",
            )
        )

    current = (now or datetime.now(UTC)).astimezone(UTC)
    points = [
        point
        for point in points
        if current - timedelta(minutes=interval_minutes) < point.forecast_time <= current + timedelta(hours=3)
    ]
    if not points or points[-1].forecast_time <= current:
        raise ProviderDataError("Buienalarm returned only stale forecast points")
    return ForecastData(tuple(points), metadata={"experimental": True})


class BuienalarmProvider(PrecipitationProvider):
    """Fetch forecasts from the undocumented Buienalarm endpoint."""

    async def async_fetch_forecast(self) -> ForecastData:
        try:
            payload = await async_get(
                self._session,
                URL.format(latitude=f"{self.latitude:.5f}", longitude=f"{self.longitude:.5f}"),
                response_type="json",
                headers=HEADERS,
            )
        except (ClientError, TimeoutError, ClientResponseError, ValueError) as err:
            raise ProviderConnectionError("Unable to fetch Buienalarm forecast") from err
        if not isinstance(payload, dict):
            raise ProviderDataError("Buienalarm returned a non-object response")
        return parse_buienalarm(payload)
