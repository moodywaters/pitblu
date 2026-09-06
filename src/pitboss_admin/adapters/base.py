"""Internal boundary implemented by physical and simulated device adapters."""

from __future__ import annotations

from typing import Protocol

from pitboss_admin.models import DeviceSnapshot, DiscoveredDevice, TelemetrySource


class AdapterError(RuntimeError):
    """Base class for safe device-adapter failures."""


class AdapterDisconnectedError(AdapterError):
    """An operation requires a live device connection."""


class UnsupportedDeviceError(AdapterError):
    """The discovered device is not a supported model."""


class DeviceAdapter(Protocol):
    """Async boundary used by discovery and future connection controllers."""

    @property
    def source(self) -> TelemetrySource: ...

    @property
    def is_connected(self) -> bool: ...

    async def discover(self, duration: float) -> tuple[DiscoveredDevice, ...]: ...

    async def recover_registered(self, identity: str) -> bool: ...

    async def connect(self, device: DiscoveredDevice) -> None: ...

    async def disconnect(self) -> None: ...

    async def read_snapshot(self) -> DeviceSnapshot: ...
