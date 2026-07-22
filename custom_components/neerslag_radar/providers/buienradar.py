"""Buienradar precipitation forecast provider."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponseError

from ..models import ForecastData, ForecastPoint
from .base import PrecipitationProvider, ProviderConnectionError, ProviderDataError
from .http import async_get

URL = "https://gpsgadget.buienradar.nl/data/raintext"
_LINE = re.compile(r"^(?P<value>\d{3})\|(?P<hour>\d{2}):(?P<minute>\d{2})$")
_AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def intensity_from_code(code: int) -> float:
    """Convert a Buienradar radar code to mm/h."""
    if code <= 0:
        return 0.0
    return 10 ** ((code - 109) / 32)


def parse_buienradar(text: str, now: datetime | None = None) -> ForecastData:
    """Parse Buienradar raintext into normalized points."""
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    now_local = now_utc.astimezone(_AMSTERDAM)
    points: list[ForecastPoint] = []
    previous: datetime | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        match = _LINE.fullmatch(line)
        if match is None:
            raise ProviderDataError(f"Invalid Buienradar line: {line!r}")
        candidate = now_local.replace(
            hour=int(match["hour"]),
            minute=int(match["minute"]),
            second=0,
            microsecond=0,
        )
        if previous is None and candidate < now_local - timedelta(minutes=10):
            candidate += timedelta(days=1)
        elif previous is not None and candidate <= previous:
            candidate += timedelta(days=1)
            if candidate - previous > timedelta(hours=1):
                raise ProviderDataError("Buienradar timestamps are duplicate or out of order")
        previous = candidate
        intensity = intensity_from_code(int(match["value"]))
        points.append(
            ForecastPoint(
                forecast_time=candidate.astimezone(UTC),
                interval_minutes=5,
                precipitation_mm=intensity / 12,
                intensity_mm_h=intensity,
                source="Buienradar",
            )
        )

    if not points:
        raise ProviderDataError("Buienradar returned no forecast points")
    return ForecastData(tuple(points), metadata={"endpoint": "raintext"})


class BuienradarProvider(PrecipitationProvider):
    """Fetch forecasts from Buienradar."""

    async def async_fetch_forecast(self) -> ForecastData:
        try:
            text = await async_get(
                self._session,
                URL,
                response_type="text",
                params={"lat": f"{self.latitude:.5f}", "lon": f"{self.longitude:.5f}"},
            )
        except (ClientError, TimeoutError, ClientResponseError) as err:
            raise ProviderConnectionError("Unable to fetch Buienradar forecast") from err
        return parse_buienradar(text)
