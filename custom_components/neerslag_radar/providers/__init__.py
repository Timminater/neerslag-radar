"""Provider factory for Neerslag Radar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import ProviderType
from .base import PrecipitationProvider
from .buienalarm import BuienalarmProvider
from .buienradar import BuienradarProvider
from .knmi import KnmiProvider, KnmiSharedCache
from .open_meteo import OpenMeteoProvider

if TYPE_CHECKING:
    from aiohttp import ClientSession


def create_provider(
    provider_type: ProviderType,
    session: ClientSession,
    latitude: float,
    longitude: float,
    data: dict[str, Any],
    knmi_cache: KnmiSharedCache | None = None,
) -> PrecipitationProvider:
    """Create a provider implementation."""
    if provider_type is ProviderType.BUIENRADAR:
        return BuienradarProvider(session, latitude, longitude)
    if provider_type is ProviderType.BUIENALARM:
        return BuienalarmProvider(session, latitude, longitude)
    if provider_type is ProviderType.OPEN_METEO:
        return OpenMeteoProvider(session, latitude, longitude)
    if provider_type is ProviderType.KNMI:
        if knmi_cache is None:
            raise ValueError("KNMI cache is required")
        return KnmiProvider(
            session,
            latitude,
            longitude,
            api_key=str(data.get("api_key", "")),
            cache=knmi_cache,
        )
    raise ValueError(f"Unsupported provider: {provider_type}")


__all__ = ["KnmiSharedCache", "PrecipitationProvider", "create_provider"]
