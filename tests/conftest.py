"""Test bootstrap.

The local Codex runtime is Python 3.12 while Home Assistant 2026.6+ requires
Python 3.14.2. Keep pure provider tests runnable locally without importing the
Home Assistant package; CI has the real package and follows the normal imports.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _namespace(name: str, path: Path) -> None:
    module = ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module


if importlib.util.find_spec("homeassistant") is None:
    root = Path(__file__).parents[1]
    custom_components = root / "custom_components"
    integration = custom_components / "neerslag_radar"
    _namespace("custom_components", custom_components)
    _namespace("custom_components.neerslag_radar", integration)
    _namespace("custom_components.neerslag_radar.providers", integration / "providers")
