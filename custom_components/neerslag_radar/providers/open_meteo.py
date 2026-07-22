"""Open-Meteo precipitation forecast provider."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientError, ClientResponseError

from ..models import ForecastData, ForecastPoint
from .base import PrecipitationProvider, ProviderConnectionError, ProviderDataError
from .http import async_get

URL = "https://api.open-meteo.com/v1/forecast"


def parse_open_meteo(payload: dict[str, Any], now: datetime | None = None) -> ForecastData:
    """Parse Open-Meteo 15-minute precipitation totals."""
    data = payload.get("minutely_15")
    if not isinstance(data, dict):
        raise ProviderDataError("Open-Meteo response has no minutely_15 data")
    times = data.get("time")
    precipitation = data.get("precipitation")
    if not isinstance(times, list) or not isinstance(precipitation, list):
        raise ProviderDataError("Open-Meteo response has invalid arrays")
    if len(times) != len(precipitation):
        raise ProviderDataError("Open-Meteo response arrays have different lengths")
    units = payload.get("minutely_15_units")
    if isinstance(units, dict) and units.get("precipitation") not in (None, "mm"):
        raise ProviderDataError("Open-Meteo precipitation unit is not millimetres")

    cutoff = (now or datetime.now(UTC)).astimezone(UTC)
    points: list[ForecastPoint] = []
    for raw_time, raw_amount in zip(times, precipitation, strict=False):
        try:
            forecast_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            forecast_time = forecast_time.replace(tzinfo=forecast_time.tzinfo or UTC).astimezone(UTC)
            amount = max(0.0, float(raw_amount))
        except (TypeError, ValueError) as err:
            raise ProviderDataError("Invalid Open-Meteo forecast point") from err
        if forecast_time <= cutoff:
            continue
        points.append(
            ForecastPoint(
                forecast_time=forecast_time,
                interval_minutes=15,
                precipitation_mm=amount,
                intensity_mm_h=amount * 4,
                source="Open-Meteo",
            )
        )
        if len(points) == 12:
            break

    if not points:
        raise ProviderDataError("Open-Meteo returned no future forecast points")
    return ForecastData(tuple(points), metadata={"model": payload.get("model")})


class OpenMeteoProvider(PrecipitationProvider):
    """Fetch forecasts from Open-Meteo."""

    async def async_fetch_forecast(self) -> ForecastData:
        try:
            payload = await async_get(
                self._session,
                URL,
                response_type="json",
                params={
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "minutely_15": "precipitation",
                    "forecast_minutely_15": 13,
                    "timezone": "UTC",
                },
            )
        except (ClientError, TimeoutError, ClientResponseError, ValueError) as err:
            raise ProviderConnectionError("Unable to fetch Open-Meteo forecast") from err
        if not isinstance(payload, dict):
            raise ProviderDataError("Open-Meteo returned a non-object response")
        return parse_open_meteo(payload)
