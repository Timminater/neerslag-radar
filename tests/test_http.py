"""Tests for bounded provider HTTP retries."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from custom_components.neerslag_radar.providers import http


class _Response:
    def __init__(self, status: int, payload: dict[str, Any], retry_after: str | None = None) -> None:
        self.status = status
        self._payload = payload
        self.headers = {"Retry-After": retry_after} if retry_after else {}
        self.content_length = None

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def read(self) -> bytes:
        return b""

    async def json(self, *, content_type: None = None) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise AssertionError(f"Unexpected terminal HTTP status {self.status}")


class _Session:
    def __init__(self, responses: Iterator[_Response]) -> None:
        self._responses = responses
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> _Response:
        self.calls += 1
        return next(self._responses)


@pytest.mark.asyncio
async def test_retry_after_is_bounded_and_request_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(http.asyncio, "sleep", record_sleep)
    session = _Session(iter([_Response(429, {}, "120"), _Response(200, {"ok": True})]))

    result = await http.async_get(session, "https://example.invalid", response_type="json")  # type: ignore[arg-type]

    assert result == {"ok": True}
    assert session.calls == 2
    assert delays == [http.MAX_RETRY_DELAY]
