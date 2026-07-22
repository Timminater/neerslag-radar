"""KNMI seamless ensemble precipitation provider."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from ..models import ForecastData, ForecastPoint
from .base import (
    PrecipitationProvider,
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderDataError,
)
from .http import async_get

DATASET = "seamless_precipitation_ensemble_forecast_members"
VERSION = "1.0"
BASE_URL = f"https://api.dataplatform.knmi.nl/open-data/v1/datasets/{DATASET}/versions/{VERSION}/files"
MAX_FILE_SIZE = 750_000_000
KNMI_ANONYMOUS_API_KEY = (
    "eyJvcmciOiI1ZTU1NGUxOTI3NGE5NjAwMDEyYTNlYjEiLCJpZCI6IjUzYTg1ZDBhMmQ5YzRkYzJi"
    "YWNlNzQ4NTQ2Zjk4ODExIiwiaCI6Im11cm11cjEyOCJ9"
)


def _select_api_key(api_key: str, use_anonymous_api_key: bool) -> str:
    """Select either the user-owned key or KNMI's published shared test key."""
    return KNMI_ANONYMOUS_API_KEY if use_anonymous_api_key else api_key.strip()


def _attribute(obj: Any, name: str, default: Any = None) -> Any:
    """Return and normalize an HDF5/NetCDF attribute."""
    if obj is None:
        return default
    value = obj.attrs.get(name, default)
    if hasattr(value, "size") and value.size == 1:
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _variables(dataset: Any) -> Any:
    """Return the variable mapping for netCDF-like and HDF5 readers."""
    return getattr(dataset, "variables", dataset)


def _dimensions(variable: Any) -> tuple[str, ...]:
    """Return semantic dimension names from a pyfive dataset."""
    if dimensions := getattr(variable, "dimensions", None):
        return tuple(dimensions)
    result: list[str] = []
    for index, dimension in enumerate(variable.dims):
        scales = list(dimension)
        result.append(scales[0].name.rsplit("/", 1)[-1] if scales else f"dim_{index}")
    return tuple(result)


def _write_temporary_file(data: bytes) -> str:
    """Write bytes to a private temporary NetCDF file."""
    descriptor, path = tempfile.mkstemp(prefix="neerslag_radar_knmi_", suffix=".nc")
    with os.fdopen(descriptor, "wb") as file_handle:
        file_handle.write(data)
    return path


class KnmiSharedCache:
    """Share the latest downloaded KNMI file between configured locations."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._lock = asyncio.Lock()
        self._filename: str | None = None
        self._path: str | None = None

    async def async_get_path(self, api_key: str) -> tuple[str, str]:
        """Return the latest local file path and source filename."""
        async with self._lock:
            filename = await self._async_latest_filename(api_key)
            cached_file_exists = bool(
                self._path and await asyncio.to_thread(Path(self._path).exists)
            )
            if filename == self._filename and self._path and cached_file_exists:
                return self._path, filename

            download_url = await self._async_download_url(api_key, filename)
            try:
                data = await async_get(
                    self._session,
                    download_url,
                    response_type="bytes",
                    max_bytes=MAX_FILE_SIZE,
                )
            except ClientResponseError as err:
                if err.status in (401, 403):
                    raise ProviderAuthenticationError("KNMI rejected the API key") from err
                raise ProviderConnectionError("Unable to download KNMI forecast") from err
            except (ClientError, TimeoutError) as err:
                raise ProviderConnectionError("Unable to download KNMI forecast") from err
            except ValueError as err:
                raise ProviderDataError("KNMI download exceeded its safety limit") from err

            path = await asyncio.to_thread(_write_temporary_file, data)
            old_path = self._path
            self._path = path
            self._filename = filename
            if old_path:
                await asyncio.to_thread(Path(old_path).unlink, missing_ok=True)
            return path, filename

    async def _async_latest_filename(self, api_key: str) -> str:
        try:
            payload = await async_get(
                self._session,
                BASE_URL,
                response_type="json",
                headers={"Authorization": api_key},
                params={"maxKeys": 1, "sorting": "desc", "orderBy": "lastModified"},
            )
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ProviderAuthenticationError("KNMI rejected the API key") from err
            raise ProviderConnectionError("Unable to list KNMI forecast files") from err
        except (ClientError, TimeoutError, ValueError) as err:
            raise ProviderConnectionError("Unable to list KNMI forecast files") from err
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list) or not files:
            raise ProviderDataError("KNMI returned no forecast files")
        filename = files[0].get("filename") if isinstance(files[0], dict) else None
        if not isinstance(filename, str) or not filename:
            raise ProviderDataError("KNMI returned an invalid filename")
        return filename

    async def _async_download_url(self, api_key: str, filename: str) -> str:
        try:
            payload = await async_get(
                self._session,
                f"{BASE_URL}/{filename}/url",
                response_type="json",
                headers={"Authorization": api_key},
            )
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise ProviderAuthenticationError("KNMI rejected the API key") from err
            raise ProviderConnectionError("Unable to obtain KNMI download URL") from err
        except (ClientError, TimeoutError, ValueError) as err:
            raise ProviderConnectionError("Unable to obtain KNMI download URL") from err
        url = payload.get("temporaryDownloadUrl") if isinstance(payload, dict) else None
        if not isinstance(url, str) or not url:
            raise ProviderDataError("KNMI returned no temporary download URL")
        return url

    async def async_validate_key(self, api_key: str) -> None:
        """Validate a KNMI key without downloading the large data file."""
        await self._async_latest_filename(api_key)

    async def async_close(self) -> None:
        """Delete the cached temporary file."""
        if self._path:
            await asyncio.to_thread(Path(self._path).unlink, missing_ok=True)
        self._path = None
        self._filename = None


def _find_data_variable(dataset: Any) -> Any:
    candidates: list[tuple[int, Any]] = []
    for name, variable in _variables(dataset).items():
        if not hasattr(variable, "shape"):
            continue
        lower = name.lower()
        standard_name = str(_attribute(variable, "standard_name", "")).lower()
        dimensions = tuple(dimension.lower() for dimension in _dimensions(variable))
        identity = f"{lower} {standard_name}"
        if len(variable.shape) < 3 or not any(
            token in identity for token in ("precip", "rain", "intensity")
        ):
            continue
        score = 0
        score += 5 if "intensity" in identity else 0
        score += 3 if any("time" in dimension for dimension in dimensions) else 0
        score += 3 if any(token in dimension for dimension in dimensions for token in ("member", "ensemble", "realization")) else 0
        candidates.append((score, variable))
    if not candidates:
        raise ProviderDataError("No precipitation variable found in KNMI file")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _dimension_index(
    dataset: Any,
    dimensions: tuple[str, ...],
    tokens: tuple[str, ...],
    *,
    axis: str | None = None,
    standard_names: tuple[str, ...] = (),
) -> int | None:
    variables = _variables(dataset)
    for index, dimension in enumerate(dimensions):
        coordinate = variables.get(dimension)
        dimension_name = dimension.lower()
        coordinate_axis = str(_attribute(coordinate, "axis", "")).upper()
        standard_name = str(_attribute(coordinate, "standard_name", "")).lower()
        units = str(_attribute(coordinate, "units", "")).lower()
        if (
            any(token in dimension_name for token in tokens)
            or (axis is not None and coordinate_axis == axis)
            or standard_name in standard_names
            or (axis == "T" and " since " in units)
        ):
            return index
    return None


def _nearest_grid_cell(dataset: Any, latitude: float, longitude: float) -> tuple[int, int]:
    import numpy as np

    coordinate_tolerance = 1e-4
    variables = _variables(dataset)

    lat_variable = next(
        (variables[name] for name in ("lat", "latitude") if name in variables), None
    )
    lon_variable = next(
        (variables[name] for name in ("lon", "longitude") if name in variables), None
    )
    if lat_variable is not None and lon_variable is not None and lat_variable.ndim == lon_variable.ndim == 1:
        latitudes = np.asarray(lat_variable[:], dtype=float)
        longitudes = np.asarray(lon_variable[:], dtype=float)
        if not (
            np.nanmin(latitudes) - coordinate_tolerance
            <= latitude
            <= np.nanmax(latitudes) + coordinate_tolerance
            and np.nanmin(longitudes) - coordinate_tolerance
            <= longitude
            <= np.nanmax(longitudes) + coordinate_tolerance
        ):
            raise ProviderDataError("Location is outside the KNMI forecast grid")
        return int(np.nanargmin(abs(latitudes - latitude))), int(
            np.nanargmin(abs(longitudes - longitude))
        )
    if lat_variable is not None and lon_variable is not None and lat_variable.ndim == lon_variable.ndim == 2:
        latitudes = np.asarray(lat_variable[:], dtype=float)
        longitudes = np.asarray(lon_variable[:], dtype=float)
        if not (
            np.nanmin(latitudes) - coordinate_tolerance
            <= latitude
            <= np.nanmax(latitudes) + coordinate_tolerance
            and np.nanmin(longitudes) - coordinate_tolerance
            <= longitude
            <= np.nanmax(longitudes) + coordinate_tolerance
        ):
            raise ProviderDataError("Location is outside the KNMI forecast grid")
        distance = (latitudes - latitude) ** 2 + ((longitudes - longitude) * np.cos(np.deg2rad(latitude))) ** 2
        flat_index = int(np.nanargmin(distance))
        return tuple(int(value) for value in np.unravel_index(flat_index, distance.shape))  # type: ignore[return-value]

    raise ProviderDataError("KNMI file has no supported latitude/longitude grid")


def _unit_mode(variable: Any) -> str:
    """Return whether a variable contains intensity or interval amounts."""
    units = str(_attribute(variable, "units", "")).lower().replace(" ", "")
    if not units:
        return "intensity"
    if "mm" in units and any(
        token in units for token in ("h-1", "h^-1", "/h", "hour-1")
    ):
        return "intensity"
    if units in {"mm", "kgm-2"}:
        return "amount"
    if units in {"kgm-2s-1", "mm/s"}:
        return "flux"
    raise ProviderDataError(f"Unsupported KNMI precipitation unit: {units}")


def _decode_forecast_times(variable: Any, count: int) -> list[datetime]:
    """Decode the small CF time subset without a binary NetCDF dependency."""
    units = str(_attribute(variable, "units", ""))
    match = re.fullmatch(r"(seconds|minutes|hours) since (.+)", units, re.IGNORECASE)
    if not match:
        raise ProviderDataError(f"Unsupported KNMI time unit: {units}")
    unit, origin_text = match.groups()
    origin_text = origin_text.strip().replace("Z", "+00:00")
    try:
        origin = datetime.fromisoformat(origin_text)
    except ValueError as err:
        raise ProviderDataError(f"Unsupported KNMI time origin: {origin_text}") from err
    if origin.tzinfo is None:
        origin = origin.replace(tzinfo=UTC)
    else:
        origin = origin.astimezone(UTC)
    seconds_per_unit = {"seconds": 1, "minutes": 60, "hours": 3600}[unit.lower()]
    return [
        origin + timedelta(seconds=float(value) * seconds_per_unit)
        for value in variable[:count]
    ]


def _scaled_values(variable: Any, selection: tuple[Any, ...]) -> Any:
    """Read a subset and apply NetCDF fill, scale and offset metadata."""
    import numpy as np

    raw = np.asarray(variable[selection])
    values = raw.astype(float)
    fill_value = _attribute(variable, "_FillValue")
    if fill_value is not None:
        values[raw == fill_value] = np.nan
    values *= float(_attribute(variable, "scale_factor", 1.0))
    values += float(_attribute(variable, "add_offset", 0.0))
    return values


def parse_knmi_file(path: str, latitude: float, longitude: float) -> ForecastData:
    """Extract one location and the first three hours from a KNMI NetCDF file."""
    import numpy as np
    import pyfive

    try:
        with pyfive.File(path, "r") as dataset:
            variable = _find_data_variable(dataset)
            dimensions = _dimensions(variable)
            time_axis = _dimension_index(
                dataset,
                dimensions,
                ("time", "leadtime", "forecast_period"),
                axis="T",
                standard_names=("time", "forecast_period"),
            )
            member_axis = _dimension_index(
                dataset,
                dimensions,
                ("member", "ensemble", "realization"),
                standard_names=("realization",),
            )
            y_axis = _dimension_index(
                dataset,
                dimensions,
                ("y", "latitude"),
                axis="Y",
                standard_names=("projection_y_coordinate", "latitude"),
            )
            x_axis = _dimension_index(
                dataset,
                dimensions,
                ("x", "longitude"),
                axis="X",
                standard_names=("projection_x_coordinate", "longitude"),
            )
            if time_axis is None or y_axis is None or x_axis is None:
                raise ProviderDataError(f"Unsupported KNMI dimensions: {dimensions}")
            y_index, x_index = _nearest_grid_cell(dataset, latitude, longitude)

            selection: list[Any] = [0] * len(variable.shape)
            remaining_dimensions: list[str] = []
            for axis, dimension in enumerate(dimensions):
                if axis == time_axis:
                    selection[axis] = slice(0, 36)
                    remaining_dimensions.append(dimension)
                elif axis == member_axis:
                    selection[axis] = slice(0, 20)
                    remaining_dimensions.append(dimension)
                elif axis == y_axis:
                    selection[axis] = y_index
                elif axis == x_axis:
                    selection[axis] = x_index
                else:
                    selection[axis] = 0

            values = _scaled_values(variable, tuple(selection))
            unit_mode = _unit_mode(variable)
            current_time_axis = remaining_dimensions.index(dimensions[time_axis])
            if member_axis is not None:
                current_member_axis = remaining_dimensions.index(dimensions[member_axis])
                values = np.moveaxis(
                    values, (current_time_axis, current_member_axis), (0, 1)
                )
            else:
                values = np.moveaxis(values, current_time_axis, 0)
                values = values[:, np.newaxis]

            time_variable = _variables(dataset).get(dimensions[time_axis])
            forecast_times: list[datetime] = []
            if time_variable is not None and _attribute(time_variable, "units"):
                forecast_times = _decode_forecast_times(time_variable, values.shape[0])
            else:
                base = datetime.now(UTC).replace(second=0, microsecond=0)
                forecast_times = [base + timedelta(minutes=5 * (index + 1)) for index in range(values.shape[0])]

            points: list[ForecastPoint] = []
            for index, forecast_time in enumerate(forecast_times[:36]):
                members = values[index]
                finite = members[np.isfinite(members)]
                if finite.size == 0:
                    continue
                intensity = max(0.0, float(np.mean(finite)))
                if unit_mode == "flux":
                    intensity_members = np.maximum(finite, 0) * 3600
                    intensity = max(0.0, float(np.mean(intensity_members)))
                    amount_members = intensity_members / 12
                    amount = intensity / 12
                elif unit_mode == "amount":
                    amount_members = np.maximum(finite, 0)
                    amount = max(0.0, float(np.mean(amount_members)))
                    intensity_members = amount_members * 12
                    intensity = max(0.0, float(np.mean(intensity_members)))
                else:
                    intensity_members = np.maximum(finite, 0)
                    amount_members = intensity_members / 12
                    intensity = max(0.0, float(np.mean(intensity_members)))
                    amount = intensity / 12
                points.append(
                    ForecastPoint(
                        forecast_time=forecast_time,
                        interval_minutes=5,
                        precipitation_mm=amount,
                        intensity_mm_h=intensity,
                        probability=float(np.mean(intensity_members > 0.1) * 100),
                        uncertainty_mm=float(np.std(amount_members)),
                        source="KNMI",
                    )
                )
    except ProviderDataError:
        raise
    except Exception as err:
        raise ProviderDataError("Unable to parse KNMI NetCDF forecast") from err

    if not points:
        raise ProviderDataError("KNMI returned no usable forecast points")
    return ForecastData(tuple(points), metadata={"ensemble_members": int(values.shape[1])})


class KnmiProvider(PrecipitationProvider):
    """Fetch and sample KNMI ensemble forecasts."""

    request_timeout = 180

    def __init__(
        self,
        session: ClientSession,
        latitude: float,
        longitude: float,
        api_key: str,
        use_anonymous_api_key: bool,
        cache: KnmiSharedCache,
    ) -> None:
        super().__init__(session, latitude, longitude)
        self._api_key = _select_api_key(api_key, use_anonymous_api_key)
        self._cache = cache

    async def async_validate(self) -> None:
        if not self._api_key:
            raise ProviderAuthenticationError("A KNMI API key is required")
        await self._cache.async_validate_key(self._api_key)

    async def async_fetch_forecast(self) -> ForecastData:
        if not self._api_key:
            raise ProviderAuthenticationError("A KNMI API key is required")
        path, filename = await self._cache.async_get_path(self._api_key)
        data = await asyncio.to_thread(parse_knmi_file, path, self.latitude, self.longitude)
        return ForecastData(data.points, data.source_updated_at, {**data.metadata, "filename": filename})
