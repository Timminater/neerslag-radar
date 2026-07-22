"""Coordinator for the calculated Global precipitation forecast."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .aggregation import aggregate_global_forecast
from .const import DOMAIN
from .coordinator import PrecipitationCoordinator
from .models import ForecastData


class GlobalPrecipitationCoordinator(DataUpdateCoordinator[ForecastData]):
    """Recalculate the maximum whenever a provider coordinator changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        provider_coordinators: dict[str, PrecipitationCoordinator],
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__package__),
            config_entry=config_entry,
            name=f"{DOMAIN}_global",
            update_interval=None,
            always_update=False,
        )
        self._provider_coordinators = provider_coordinators
        self._unsubscribers: list[Callable[[], None]] = []

    @callback
    def async_start(self) -> None:
        """Subscribe to provider updates and publish the initial forecast."""
        self._unsubscribers.extend(
            coordinator.async_add_listener(self._handle_provider_update)
            for coordinator in self._provider_coordinators.values()
        )
        self._handle_provider_update()

    @callback
    def async_stop(self) -> None:
        """Stop listening to provider coordinators."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    @callback
    def _handle_provider_update(self) -> None:
        provider_data = {
            coordinator.provider_type.value: coordinator.data
            for coordinator in self._provider_coordinators.values()
            if coordinator.last_update_success and coordinator.data is not None
        }
        data = aggregate_global_forecast(provider_data)
        if not data.points:
            self.async_set_update_error(
                UpdateFailed("No current provider forecasts are available")
            )
            return
        self.async_set_updated_data(data)
