"""Base classes and errors for precipitation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from ..models import ForecastData


class ProviderError(Exception):
    """Base provider error."""


class ProviderAuthenticationError(ProviderError):
    """Provider rejected authentication."""


class ProviderConnectionError(ProviderError):
    """Provider could not be reached."""


class ProviderDataError(ProviderError):
    """Provider returned malformed or unsupported data."""


class PrecipitationProvider(ABC):
    """Abstract precipitation provider."""

    request_timeout = 30

    def __init__(self, session: ClientSession, latitude: float, longitude: float) -> None:
        self._session = session
        self.latitude = latitude
        self.longitude = longitude

    @abstractmethod
    async def async_fetch_forecast(self) -> ForecastData:
        """Fetch and normalize a forecast."""

    async def async_validate(self) -> None:
        """Validate provider configuration."""
        await self.async_fetch_forecast()
