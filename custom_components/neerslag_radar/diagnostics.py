"""Diagnostics for Neerslag Radar."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import PrecipitationConfigEntry
from .const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE

TO_REDACT = {CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, "filename", "endpoint"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PrecipitationConfigEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a location."""
    providers: dict[str, Any] = {}
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        subentry = entry.runtime_data.subentries[subentry_id]
        providers[subentry_id] = {
            "data": async_redact_data(dict(subentry.data), TO_REDACT),
            "last_update_success": coordinator.last_update_success,
            "point_count": len(coordinator.data.points) if coordinator.data else 0,
            "metadata": async_redact_data(coordinator.data.metadata, TO_REDACT)
            if coordinator.data
            else {},
        }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "providers": providers,
    }
