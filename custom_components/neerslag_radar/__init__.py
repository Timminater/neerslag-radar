"""Neerslag Radar integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    PROVIDERS,
    SUBENTRY_TYPE_PROVIDER,
    ProviderType,
)
from .coordinator import PrecipitationCoordinator
from .providers import KnmiSharedCache, create_provider

CACHE_KEY = "knmi_cache"
CACHE_USERS_KEY = "knmi_cache_users"


@dataclass(slots=True)
class PrecipitationRuntimeData:
    """Runtime data attached to a location config entry."""

    coordinators: dict[str, PrecipitationCoordinator]
    subentries: dict[str, ConfigSubentry]
    knmi_cache: KnmiSharedCache


PrecipitationConfigEntry = ConfigEntry[PrecipitationRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: PrecipitationConfigEntry) -> bool:
    """Set up a location and all provider subentries."""
    session = async_get_clientsession(hass)
    domain_data = hass.data.setdefault(DOMAIN, {})
    knmi_cache = domain_data.get(CACHE_KEY)
    if not isinstance(knmi_cache, KnmiSharedCache):
        knmi_cache = KnmiSharedCache(session)
        domain_data[CACHE_KEY] = knmi_cache
        domain_data[CACHE_USERS_KEY] = 0
    domain_data[CACHE_USERS_KEY] = int(domain_data[CACHE_USERS_KEY]) + 1
    coordinators: dict[str, PrecipitationCoordinator] = {}
    provider_subentries: dict[str, ConfigSubentry] = {}

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PROVIDER:
            continue
        provider_type = ProviderType(subentry.data[CONF_PROVIDER])
        definition = PROVIDERS[provider_type]
        provider = create_provider(
            provider_type,
            session,
            float(entry.data[CONF_LATITUDE]),
            float(entry.data[CONF_LONGITUDE]),
            dict(subentry.data),
            knmi_cache,
        )
        coordinator = PrecipitationCoordinator(
            hass,
            entry,
            provider_type,
            provider,
            int(subentry.data.get(CONF_SCAN_INTERVAL, definition.default_interval)),
        )
        coordinators[subentry.subentry_id] = coordinator
        provider_subentries[subentry.subentry_id] = subentry

    entry.runtime_data = PrecipitationRuntimeData(coordinators, provider_subentries, knmi_cache)
    if coordinators:
        await asyncio.gather(
            *(coordinator.async_refresh() for coordinator in coordinators.values()),
            return_exceptions=True,
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PrecipitationConfigEntry) -> bool:
    """Unload a location config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        domain_data = hass.data[DOMAIN]
        domain_data[CACHE_USERS_KEY] = max(0, int(domain_data[CACHE_USERS_KEY]) - 1)
        if domain_data[CACHE_USERS_KEY] == 0:
            await entry.runtime_data.knmi_cache.async_close()
            domain_data.pop(CACHE_KEY, None)
            domain_data.pop(CACHE_USERS_KEY, None)
            if not domain_data:
                hass.data.pop(DOMAIN, None)
    return unloaded
