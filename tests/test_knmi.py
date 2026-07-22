"""Tests for KNMI NetCDF extraction."""

from datetime import UTC, datetime
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from custom_components.neerslag_radar.providers.knmi import (
    KNMI_ANONYMOUS_API_KEY,
    _select_api_key,
    parse_knmi_file,
)


def _write_fixture(path: Path, dimensions: tuple[str, ...]) -> None:
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 4)
        dataset.createDimension("realization", 3)
        dataset.createDimension("y", 2)
        dataset.createDimension("x", 3)

        time = dataset.createVariable("time", "i4", ("time",))
        time.units = "minutes since 2026-07-22 10:00:00 +00:00"
        time[:] = [5, 10, 15, 20]
        realization = dataset.createVariable("realization", "i4", ("realization",))
        realization.standard_name = "realization"
        realization[:] = [0, 1, 2]
        lat = dataset.createVariable("latitude", "f4", ("y", "x"))
        lon = dataset.createVariable("longitude", "f4", ("y", "x"))
        lat[:, :] = np.asarray(
            [[52.0, 52.0, 52.0], [52.1, 52.1, 52.1]], dtype=np.float32
        )
        lon[:, :] = np.asarray(
            [[5.0, 5.1, 5.2], [5.0, 5.1, 5.2]], dtype=np.float32
        )

        variable = dataset.createVariable("precipitation_intensity", "f4", dimensions)
        canonical = np.zeros((4, 3, 2, 3), dtype=np.float32)
        canonical[:, :, 1, 1] = [
            [0.0, 1.2, 2.4],
            [1.2, 1.2, 1.2],
            [0.0, 0.0, 0.0],
            [2.4, 3.6, 4.8],
        ]
        order = tuple(("time", "realization", "y", "x").index(item) for item in dimensions)
        variable[...] = np.transpose(canonical, axes=order).copy()


@pytest.mark.parametrize(
    "dimensions",
    [
        ("time", "realization", "y", "x"),
        ("realization", "time", "y", "x"),
    ],
)
def test_parse_knmi_semantic_dimensions(tmp_path: Path, dimensions: tuple[str, ...]) -> None:
    path = tmp_path / "forecast.nc"
    _write_fixture(path, dimensions)

    result = parse_knmi_file(str(path), 52.1, 5.1)

    assert len(result.points) == 4
    assert result.points[0].forecast_time == datetime(2026, 7, 22, 10, 5, tzinfo=UTC)
    assert result.points[0].intensity_mm_h == pytest.approx(1.2)
    assert result.points[0].precipitation_mm == pytest.approx(0.1)
    assert result.points[0].probability == pytest.approx(200 / 3)
    assert result.metadata["ensemble_members"] == 3


def test_parse_knmi_packed_values_like_live_dataset(tmp_path: Path) -> None:
    """Apply scale metadata from KNMI's packed unsigned integer values."""
    path = tmp_path / "packed-forecast.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("ens_number", 2)
        dataset.createDimension("time", 1)
        dataset.createDimension("y", 1)
        dataset.createDimension("x", 1)

        ensemble = dataset.createVariable("ens_number", "i4", ("ens_number",))
        ensemble.standard_name = "realization"
        ensemble[:] = [0, 1]
        time = dataset.createVariable("time", "i4", ("time",))
        time.units = "seconds since 2026-07-22 22:20:00"
        time[:] = [300]
        latitude = dataset.createVariable("lat", "f8", ("y", "x"))
        longitude = dataset.createVariable("lon", "f8", ("y", "x"))
        latitude[:] = [[52.1]]
        longitude[:] = [[5.1]]
        precipitation = dataset.createVariable(
            "precip_intensity", "u2", ("ens_number", "time", "y", "x")
        )
        precipitation.scale_factor = 0.01
        precipitation.add_offset = 0.0
        precipitation.set_auto_maskandscale(False)
        precipitation[:] = np.asarray([[[[100]]], [[[200]]]], dtype=np.uint16)

    result = parse_knmi_file(str(path), 52.1, 5.1)

    assert result.points[0].intensity_mm_h == pytest.approx(1.5)
    assert result.points[0].precipitation_mm == pytest.approx(0.125)
    assert result.points[0].probability == 100


def test_selects_personal_or_shared_anonymous_api_key() -> None:
    """The checkbox selects the published key without storing it in config data."""
    assert _select_api_key(" personal-key ", False) == "personal-key"
    assert _select_api_key("", True) == KNMI_ANONYMOUS_API_KEY
