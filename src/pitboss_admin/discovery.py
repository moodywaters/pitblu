"""Scheduled discovery supervisor that avoids continuous radio scanning."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pitboss_admin.adapters.base import DeviceAdapter
from pitboss_admin.models import DiscoveredDevice

DiscoveryCallback = Callable[[tuple[DiscoveredDevice, ...]], Awaitable[None]]


class DiscoverySupervisor:
    def __init__(
        self,
        adapter: DeviceAdapter,
        *,
        scan_duration: float = 5.0,
        missing_interval: float = 15.0,
        connected_interval: float = 60.0,
        on_results: DiscoveryCallback | None = None,
    ) -> None:
        if min(scan_duration, missing_interval, connected_interval) <= 0:
            raise ValueError("discovery timings must be positive")
        self._adapter = adapter
        self._scan_duration = scan_duration
        self._missing_interval = missing_interval
        self._connected_interval = connected_interval
        self._on_results = on_results
        self._stop = asyncio.Event()

    async def scan_once(self) -> tuple[DiscoveredDevice, ...]:
        results = await self._adapter.discover(self._scan_duration)
        if self._on_results is not None:
            await self._on_results(results)
        return results

    def next_interval(self) -> float:
        return self._connected_interval if self._adapter.is_connected else self._missing_interval

    async def run(self) -> None:
        while not self._stop.is_set():
            await self.scan_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.next_interval())
            except TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()
