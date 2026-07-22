"""Data update coordinator for Neerslag Radar."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_REQUEST_TIMEOUT, DOMAIN, ProviderType
from .models import ForecastData
from .providers.base import PrecipitationProvider, ProviderError


class PrecipitationCoordinator(DataUpdateCoordinator[ForecastData]):
    """Coordinate updates for one provider subentry."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider_type: ProviderType,
        provider: PrecipitationProvider,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__package__),
            config_entry=config_entry,
            name=f"{DOMAIN}_{provider_type}",
            update_interval=timedelta(minutes=scan_interval),
            always_update=False,
        )
        self.provider_type = provider_type
        self.provider = provider

    async def _async_update_data(self) -> ForecastData:
        try:
            async with asyncio.timeout(
                getattr(self.provider, "request_timeout", DEFAULT_REQUEST_TIMEOUT)
            ):
                return await self.provider.async_fetch_forecast()
        except ProviderError as err:
            raise UpdateFailed(str(err)) from err
        except TimeoutError as err:
            raise UpdateFailed(f"{self.provider_type} request timed out") from err
