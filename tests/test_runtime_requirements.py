"""Tests for optional runtime dependencies."""

from __future__ import annotations

import json
from pathlib import Path


def test_manifest_uses_pure_python_knmi_reader() -> None:
    """KNMI must not require platform-specific NetCDF or projection wheels."""
    manifest_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "neerslag_radar"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["requirements"] == ["pyfive==1.1.2"]
