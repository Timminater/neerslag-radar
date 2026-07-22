"""Tests for optional runtime dependencies."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from custom_components.neerslag_radar.providers.base import ProviderDependencyError
from custom_components.neerslag_radar.providers.knmi import _require_knmi_dependencies


def test_manifest_has_no_mandatory_binary_requirements() -> None:
    """One experimental provider must not block the complete integration."""
    manifest_path = (
        Path(__file__).parents[1]
        / "custom_components"
        / "neerslag_radar"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert not manifest.get("requirements")


def test_knmi_checks_optional_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """KNMI fails before network access when its parser cannot be loaded."""
    knmi_module = importlib.import_module("custom_components.neerslag_radar.providers.knmi")
    monkeypatch.setattr(knmi_module, "knmi_dependencies_available", lambda: False)

    with pytest.raises(ProviderDependencyError):
        _require_knmi_dependencies()
