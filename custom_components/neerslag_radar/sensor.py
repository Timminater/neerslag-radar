"""Sensors for Neerslag Radar."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPrecipitationDepth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PrecipitationConfigEntry
from .const import CONF_PROVIDER, DOMAIN, PROVIDERS, ProviderType
from .coordinator import PrecipitationCoordinator
from .models import ForecastPoint


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PrecipitationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up provider forecast sensors."""
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        subentry = entry.runtime_data.subentries[subentry_id]
        provider_type = ProviderType(subentry.data[CONF_PROVIDER])
        entities: list[SensorEntity] = [
            PrecipitationOverviewSensor(entry, subentry_id, coordinator, provider_type)
        ]
        entities.extend(
            PrecipitationSlotSensor(entry, subentry_id, coordinator, provider_type, slot)
            for slot in range(PROVIDERS[provider_type].slot_count)
        )
        async_add_entities(entities, config_subentry_id=subentry_id)


class PrecipitationSensorBase(CoordinatorEntity[PrecipitationCoordinator], SensorEntity):
    """Base class for provider sensors."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_native_unit_of_measurement = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        entry: PrecipitationConfigEntry,
        subentry_id: str,
        coordinator: PrecipitationCoordinator,
        provider_type: ProviderType,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._subentry_id = subentry_id
        self._provider_type = provider_type
        definition = PROVIDERS[provider_type]
        self._attr_attribution = definition.attribution
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{subentry_id}")},
            name=f"{entry.title} {definition.title}",
            manufacturer=definition.title,
            model="Neerslag forecast",
            configuration_url=_provider_url(provider_type),
        )


class PrecipitationOverviewSensor(PrecipitationSensorBase):
    """Total and full forecast for a provider."""

    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(
        self,
        entry: PrecipitationConfigEntry,
        subentry_id: str,
        coordinator: PrecipitationCoordinator,
        provider_type: ProviderType,
    ) -> None:
        super().__init__(entry, subentry_id, coordinator, provider_type)
        self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_total"
        self._attr_translation_key = "forecast_total"

    @property
    def native_value(self) -> float | None:
        """Return total expected precipitation over the available horizon."""
        if self.coordinator.data is None:
            return None
        return round(self.coordinator.data.total_precipitation_mm, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the complete compact forecast."""
        if self.coordinator.data is None:
            return {}
        points = self.coordinator.data.points
        return {
            "provider": self._provider_type.value,
            "forecast": [point.as_dict() for point in points],
            "forecast_start": points[0].forecast_time.isoformat() if points else None,
            "forecast_end": points[-1].forecast_time.isoformat() if points else None,
            "point_count": len(points),
        }


class PrecipitationSlotSensor(PrecipitationSensorBase):
    """One relative forecast slot."""

    def __init__(
        self,
        entry: PrecipitationConfigEntry,
        subentry_id: str,
        coordinator: PrecipitationCoordinator,
        provider_type: ProviderType,
        slot: int,
    ) -> None:
        super().__init__(entry, subentry_id, coordinator, provider_type)
        self._slot = slot
        self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_slot_{slot + 1}"
        self._attr_translation_key = "forecast_slot"
        self._attr_translation_placeholders = {"slot": str(slot + 1)}

    @property
    def available(self) -> bool:
        """Return availability for this specific slot."""
        return super().available and self._point is not None

    @property
    def native_value(self) -> float | None:
        """Return forecast precipitation for this interval."""
        point = self._point
        return round(point.precipitation_mm, 3) if point else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return normalized forecast details."""
        point = self._point
        if point is None:
            return {"provider": self._provider_type.value, "slot": self._slot + 1}
        result = point.as_dict()
        result.update({"provider": self._provider_type.value, "slot": self._slot + 1})
        return result

    @property
    def _point(self) -> ForecastPoint | None:
        data = self.coordinator.data
        if data is None or self._slot >= len(data.points):
            return None
        return data.points[self._slot]


def _provider_url(provider_type: ProviderType) -> str:
    return {
        ProviderType.BUIENRADAR: "https://www.buienradar.nl",
        ProviderType.BUIENALARM: "https://www.buienalarm.nl",
        ProviderType.KNMI: "https://dataplatform.knmi.nl",
        ProviderType.OPEN_METEO: "https://open-meteo.com",
    }[provider_type]
