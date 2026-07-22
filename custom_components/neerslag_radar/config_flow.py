"""Config flows for Neerslag Radar."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    FlowType,
    SubentryFlowContext,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_REQUEST_TIMEOUT,
    DOMAIN,
    PROVIDERS,
    SUBENTRY_TYPE_PROVIDER,
    ProviderType,
)
from .providers import KnmiSharedCache, create_provider
from .providers.base import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderDataError,
)


class PrecipitationForecastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a fixed forecast location."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported provider subentries."""
        return {SUBENTRY_TYPE_PROVIDER: ProviderSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create a location config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = _location_unique_id(user_input[CONF_LATITUDE], user_input[CONF_LONGITUDE])
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=self.hass.config.location_name or "Home"): cv.string,
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): cv.longitude,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the fixed location."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            unique_id = _location_unique_id(
                user_input[CONF_LATITUDE], user_input[CONF_LONGITUDE]
            )
            if any(
                other.entry_id != entry.entry_id and other.unique_id == unique_id
                for other in self.hass.config_entries.async_entries(DOMAIN)
            ):
                return self.async_abort(reason="already_configured")
            return self.async_update_reload_and_abort(
                entry,
                unique_id=unique_id,
                title=user_input[CONF_NAME],
                data=user_input,
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=entry.title): cv.string,
                vol.Required(CONF_LATITUDE, default=entry.data[CONF_LATITUDE]): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=entry.data[CONF_LONGITUDE]): cv.longitude,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)

    async def async_on_create_entry(self, result: ConfigFlowResult) -> ConfigFlowResult:
        """Open the provider flow immediately after creating a location."""
        subentry_result = await self.hass.config_entries.subentries.async_init(
            (result["result"].entry_id, SUBENTRY_TYPE_PROVIDER),
            context=SubentryFlowContext(source=SOURCE_USER),
        )
        result["next_flow"] = (FlowType.CONFIG_SUBENTRIES_FLOW, subentry_result["flow_id"])
        return result


class ProviderSubentryFlow(ConfigSubentryFlow):
    """Add or reconfigure a provider for a location."""

    def __init__(self) -> None:
        self._selected_provider: ProviderType | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Choose a provider."""
        entry = self._get_entry()
        configured = {
            ProviderType(subentry.data[CONF_PROVIDER])
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_PROVIDER
        }
        available = [provider for provider in ProviderType if provider not in configured]
        if not available:
            return self.async_abort(reason="all_providers_configured")

        if user_input is not None:
            self._selected_provider = ProviderType(user_input[CONF_PROVIDER])
            return await self._async_provider_form(self._selected_provider.value)

        selector = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": provider.value, "label": PROVIDERS[provider].title}
                    for provider in available
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_PROVIDER): selector}),
        )

    async def async_step_buienradar(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._selected_provider = ProviderType.BUIENRADAR
        return await self._async_provider_form("buienradar", user_input)

    async def async_step_buienalarm(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._selected_provider = ProviderType.BUIENALARM
        return await self._async_provider_form("buienalarm", user_input)

    async def async_step_knmi(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._selected_provider = ProviderType.KNMI
        return await self._async_provider_form("knmi", user_input)

    async def async_step_open_meteo(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._selected_provider = ProviderType.OPEN_METEO
        return await self._async_provider_form("open_meteo", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure provider credentials or polling."""
        subentry = self._get_reconfigure_subentry()
        self._selected_provider = ProviderType(subentry.data[CONF_PROVIDER])
        return await self._async_provider_form("reconfigure", user_input, dict(subentry.data))

    async def _async_provider_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        provider_type = self._selected_provider
        if provider_type is None:
            return self.async_abort(reason="unknown")
        definition = PROVIDERS[provider_type]
        defaults = defaults or {}
        errors: dict[str, str] = {}

        if user_input is not None:
            provider_data = {
                CONF_PROVIDER: provider_type.value,
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
            }
            if provider_type is ProviderType.KNMI:
                provider_data[CONF_API_KEY] = user_input[CONF_API_KEY]
            try:
                await self._async_validate_provider(provider_type, provider_data)
            except ProviderAuthenticationError:
                errors["base"] = "invalid_auth"
            except ProviderConnectionError:
                errors["base"] = "cannot_connect"
            except ProviderDataError:
                errors["base"] = "invalid_data"
            except Exception:  # noqa: BLE001 - config flows must stay usable
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_RECONFIGURE:
                    return self.async_update_reload_and_abort(
                        self._get_entry(),
                        self._get_reconfigure_subentry(),
                        title=definition.title,
                        data=provider_data,
                    )
                return self.async_create_entry(
                    title=definition.title,
                    data=provider_data,
                    unique_id=provider_type.value,
                )

        fields: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=defaults.get(CONF_SCAN_INTERVAL, definition.default_interval),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=definition.minimum_interval, max=definition.maximum_interval),
            )
        }
        if provider_type is ProviderType.KNMI:
            fields[vol.Required(CONF_API_KEY, default=defaults.get(CONF_API_KEY, ""))] = (
                TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
            )
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(fields), errors=errors)

    async def _async_validate_provider(
        self, provider_type: ProviderType, provider_data: dict[str, Any]
    ) -> None:
        entry = self._get_entry()
        session = async_get_clientsession(self.hass)
        cache = KnmiSharedCache(session)
        provider = create_provider(
            provider_type,
            session,
            float(entry.data[CONF_LATITUDE]),
            float(entry.data[CONF_LONGITUDE]),
            provider_data,
            cache,
        )
        async with asyncio.timeout(DEFAULT_REQUEST_TIMEOUT):
            await provider.async_validate()


def _location_unique_id(latitude: float, longitude: float) -> str:
    return f"{float(latitude):.5f},{float(longitude):.5f}"
