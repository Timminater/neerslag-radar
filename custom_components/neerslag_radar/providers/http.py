"""Small bounded HTTP retry helpers shared by providers."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from aiohttp import ClientError, ClientResponse, ClientSession

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 15.0


def _retry_delay(response: ClientResponse, attempt: int) -> float:
    value = response.headers.get("Retry-After")
    if value:
        try:
            return min(MAX_RETRY_DELAY, max(0.0, float(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value).astimezone(UTC)
                return min(
                    MAX_RETRY_DELAY,
                    max(0.0, (retry_at - datetime.now(UTC)).total_seconds()),
                )
            except (TypeError, ValueError):
                pass
    return min(MAX_RETRY_DELAY, float(2**attempt))


async def async_get(
    session: ClientSession,
    url: str,
    *,
    response_type: Literal["bytes", "json", "text"],
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
) -> Any:
    """GET a response with bounded transient retries and Retry-After support."""
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                    await response.read()
                    await asyncio.sleep(_retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                if max_bytes is not None:
                    length = response.content_length
                    if length is not None and length > max_bytes:
                        raise ValueError("Response exceeds configured size limit")
                if response_type == "json":
                    return await response.json(content_type=None)
                if response_type == "text":
                    return await response.text()
                data = await response.read()
                if max_bytes is not None and len(data) > max_bytes:
                    raise ValueError("Response exceeds configured size limit")
                return data
        except (ClientError, TimeoutError) as err:
            last_error = err
            if attempt == MAX_ATTEMPTS - 1:
                raise
            await asyncio.sleep(min(MAX_RETRY_DELAY, float(2**attempt)))
    if last_error is not None:
        raise last_error
    raise RuntimeError("HTTP retry loop ended without a result")
