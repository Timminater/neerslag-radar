"""Constants for Neerslag Radar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "neerslag_radar"
PLATFORMS = (Platform.SENSOR,)

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"

SUBENTRY_TYPE_PROVIDER = "provider"


class ProviderType(StrEnum):
    """Supported forecast providers."""

    BUIENRADAR = "buienradar"
    BUIENALARM = "buienalarm"
    KNMI = "knmi"
    OPEN_METEO = "open_meteo"


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """Static provider capabilities."""

    title: str
    default_interval: int
    minimum_interval: int
    maximum_interval: int
    slot_count: int
    attribution: str
    experimental: bool = False


PROVIDERS: dict[ProviderType, ProviderDefinition] = {
    ProviderType.BUIENRADAR: ProviderDefinition(
        "Buienradar", 5, 5, 15, 24, "Data provided by Buienradar.nl"
    ),
    ProviderType.BUIENALARM: ProviderDefinition(
        "Buienalarm", 5, 5, 15, 26, "Data provided by Buienalarm",
        experimental=True,
    ),
    ProviderType.KNMI: ProviderDefinition(
        "KNMI", 10, 5, 30, 36, "Data provided by KNMI (CC BY 4.0)",
        experimental=True,
    ),
    ProviderType.OPEN_METEO: ProviderDefinition(
        "Open-Meteo", 15, 15, 60, 12, "Weather data by Open-Meteo.com (CC BY 4.0)"
    ),
}

DEFAULT_REQUEST_TIMEOUT = 30
MAX_FORECAST_MINUTES = 180
