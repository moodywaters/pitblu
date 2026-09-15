from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol


class CoreRequestError(RuntimeError):
    """A safe boundary error for failed pitblu-core administration requests."""


class ThermometerGateway(Protocol):
    async def reconcile(self) -> list[dict[str, Any]]: ...
    def events(self) -> AsyncIterator[dict[str, Any]]: ...
    async def start_scan(self) -> dict[str, Any]: ...
    async def scan_result(self, scan_id: str) -> dict[str, Any]: ...
    async def register_device(
        self, discovery_id: str, friendly_name: str | None = None
    ) -> dict[str, Any]: ...
    async def reconnect_device(self, device_id: str) -> dict[str, Any]: ...
    async def operation(self, operation_id: str) -> dict[str, Any]: ...


class PitbluCoreClient:
    """Concrete server-side adapter for pitblu-core; credentials never reach a browser."""

    def __init__(
        self, base_url: str, token: str | None = None, *, client_factory: Any = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client_factory = client_factory

    def _client(self, *, timeout: float | None) -> Any:
        if self._client_factory is not None:
            return self._client_factory(timeout=timeout, headers=self.headers)
        import httpx2

        return httpx2.AsyncClient(timeout=timeout, headers=self.headers)

    async def reconcile(self) -> list[dict[str, Any]]:
        async with self._client(timeout=10) as client:
            response = await client.get(f"{self.base_url}/api/v1/devices")
            response.raise_for_status()
            devices = response.json()
            state: list[dict[str, Any]] = []
            for device in devices:
                device_id = device.get("deviceId")
                detail = await client.get(f"{self.base_url}/api/v1/devices/{device_id}")
                detail.raise_for_status()
                probes = await client.get(f"{self.base_url}/api/v1/devices/{device_id}/probes")
                battery = await client.get(f"{self.base_url}/api/v1/devices/{device_id}/battery")
                probes.raise_for_status()
                battery.raise_for_status()
                state.append(detail.json() | {"probes": probes.json(), "battery": battery.json()})
            return state

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        import httpx2

        try:
            async with self._client(timeout=30) as client:
                response = await client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx2.HTTPError as exc:
            raise CoreRequestError("pitblu-core request failed") from exc

    async def start_scan(self) -> dict[str, Any]:
        return await self._json("POST", "/api/v1/scans", json={})

    async def scan_result(self, scan_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/api/v1/scans/{scan_id}")

    async def register_device(
        self, discovery_id: str, friendly_name: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "discoveryId": discovery_id,
            "connect": True,
            "automaticReconnection": True,
        }
        if friendly_name:
            body["friendlyName"] = friendly_name
        return await self._json("POST", "/api/v1/devices", json=body)

    async def reconnect_device(self, device_id: str) -> dict[str, Any]:
        return await self._json("POST", f"/api/v1/devices/{device_id}/reconnect")

    async def operation(self, operation_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/api/v1/operations/{operation_id}")

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        import httpx2

        delay = 1.0
        while True:
            try:
                async with (
                    self._client(timeout=None) as client,
                    client.stream("GET", f"{self.base_url}/api/v1/events/stream") as response,
                ):
                    response.raise_for_status()
                    delay = 1.0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            yield json.loads(line[5:].strip())
            except (httpx2.HTTPError, json.JSONDecodeError):
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
