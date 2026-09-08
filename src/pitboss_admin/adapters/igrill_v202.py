"""Production Bleak adapter for the Weber iGrill V202."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from time import monotonic
from typing import Any, TypeVar
from uuid import uuid4

from bleak import BleakClient, BleakScanner

from pitboss_admin.adapters.base import (
    AdapterDisconnectedError,
    AdapterError,
    UnsupportedDeviceError,
)
from pitboss_admin.models import (
    DeviceSnapshot,
    DiscoveredDevice,
    ProbeReading,
    TelemetrySource,
    utc_now,
)
from pitboss_admin.protocol import (
    APP_CHALLENGE,
    APP_CHALLENGE_UUID,
    BATTERY_LEVEL_UUID,
    DEVICE_CHALLENGE_UUID,
    DEVICE_RESPONSE_UUID,
    PROBE_TEMPERATURE_UUIDS,
    V202_TEMPERATURE_SERVICE_UUID,
    decode_battery_percent,
    decode_probe_temperature_c,
)

_T = TypeVar("_T")


async def _bounded(awaitable: Awaitable[_T], timeout: float, operation: str) -> _T:
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except TimeoutError as exc:
        raise AdapterError(f"{operation} timed out") from exc


class BleakIGrillV202Adapter:
    """Read-only V202 adapter with no public Bluetooth-address surface."""

    def __init__(
        self,
        *,
        name_prefix: str = "iGrill_V202-",
        connect_timeout: float = 10.0,
        initialise_timeout: float = 15.0,
        read_timeout: float = 5.0,
        battery_interval: float = 300.0,
        clock: Callable[[], float] = monotonic,
        scanner: Any = BleakScanner,
        client_factory: Callable[..., Any] = BleakClient,
    ) -> None:
        if min(connect_timeout, initialise_timeout, read_timeout, battery_interval) <= 0:
            raise ValueError("adapter timeouts must be positive")
        self._name_prefix = name_prefix
        self._connect_timeout = connect_timeout
        self._initialise_timeout = initialise_timeout
        self._read_timeout = read_timeout
        self._scanner = scanner
        self._client_factory = client_factory
        self._native_by_id: dict[str, object] = {}
        self._client: Any | None = None
        self._sequence = 0
        self._battery_interval = battery_interval
        self._clock = clock
        self._battery_due = 0.0
        self._battery_percent: int | None = None
        self._battery_observed_at: datetime | None = None

    @property
    def source(self) -> TelemetrySource:
        return TelemetrySource.PHYSICAL

    @property
    def is_connected(self) -> bool:
        return bool(self._client is not None and self._client.is_connected)

    async def discover(self, duration: float) -> tuple[DiscoveredDevice, ...]:
        if duration <= 0:
            raise ValueError("scan duration must be positive")
        results = await _bounded(
            self._scanner.discover(timeout=duration, return_adv=True),
            duration + 1.0,
            "BLE scan",
        )
        discovered: list[DiscoveredDevice] = []
        self._native_by_id.clear()
        for native, advertisement in results.values():
            name = advertisement.local_name or native.name or ""
            services = {uuid.lower() for uuid in advertisement.service_uuids}
            if not name.startswith(self._name_prefix) and (
                V202_TEMPERATURE_SERVICE_UUID not in services
            ):
                continue
            discovery_id = uuid4().hex
            self._native_by_id[discovery_id] = native
            discovered.append(
                DiscoveredDevice(
                    discovery_id=discovery_id,
                    name=name or "Weber iGrill V202",
                    model="igrill-v202",
                    rssi=advertisement.rssi,
                    _native=native,
                    _identity=getattr(native, "address", None),
                )
            )
        return tuple(discovered)

    async def recover_registered(self, identity: str) -> bool:
        from pitboss_admin.bluez import release_registered_connection

        return await release_registered_connection(identity)

    async def connect(self, device: DiscoveredDevice) -> None:
        if self.is_connected:
            return
        native = self._native_by_id.get(device.discovery_id)
        if native is None or device.model != "igrill-v202":
            raise UnsupportedDeviceError("device is not a current supported discovery result")

        client = self._client_factory(
            native,
            timeout=self._connect_timeout,
            pair=True,
            disconnected_callback=self._on_disconnect,
        )
        try:
            await _bounded(
                client.connect(),
                self._connect_timeout,
                "BLE connection and GATT service resolution",
            )
            services = {service.uuid.lower() for service in client.services}
            if V202_TEMPERATURE_SERVICE_UUID not in services:
                raise UnsupportedDeviceError("device does not expose the V202 service")
            await self._authenticate(client)
        except BaseException:
            if client.is_connected:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(client.disconnect(), timeout=5.0)
            raise
        self._client = client
        self._battery_due = self._clock()
        self._battery_percent = None
        self._battery_observed_at = None

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), timeout=5.0)

    async def read_snapshot(self) -> DeviceSnapshot:
        client = self._client
        if client is None or not client.is_connected:
            raise AdapterDisconnectedError("V202 is not connected")

        self._sequence += 1
        observed_at = utc_now()
        if self._battery_percent is None or self._clock() >= self._battery_due:
            try:
                battery_payload = bytes(
                    await _bounded(
                        client.read_gatt_char(BATTERY_LEVEL_UUID),
                        self._read_timeout,
                        "battery read",
                    )
                )
                self._battery_percent = decode_battery_percent(battery_payload)
            except Exception:
                self._battery_percent = None
            self._battery_observed_at = utc_now()
            self._battery_due = self._clock() + self._battery_interval

        probes: list[ProbeReading] = []
        for number, characteristic in enumerate(PROBE_TEMPERATURE_UUIDS, start=1):
            try:
                payload = bytes(
                    await _bounded(
                        client.read_gatt_char(characteristic),
                        self._read_timeout,
                        f"probe {number} read",
                    )
                )
                temperature = decode_probe_temperature_c(payload)
            except Exception as exc:
                probes.append(
                    ProbeReading(
                        number=number,
                        available=False,
                        present=False,
                        temperature_c=None,
                        observed_at=observed_at,
                        sequence=self._sequence,
                        source=self.source,
                        error_code=type(exc).__name__,
                    )
                )
            else:
                probes.append(
                    ProbeReading(
                        number=number,
                        available=True,
                        present=temperature is not None,
                        temperature_c=temperature,
                        observed_at=observed_at,
                        sequence=self._sequence,
                        source=self.source,
                    )
                )

        return DeviceSnapshot(
            model="igrill-v202",
            probes=tuple(probes),
            battery_percent=self._battery_percent,
            battery_available=self._battery_percent is not None,
            battery_observed_at=self._battery_observed_at,
            observed_at=observed_at,
            sequence=self._sequence,
            source=self.source,
        )

    async def _authenticate(self, client: Any) -> None:
        await _bounded(
            client.write_gatt_char(APP_CHALLENGE_UUID, APP_CHALLENGE, response=True),
            self._initialise_timeout,
            "application challenge write",
        )
        challenge = bytes(
            await _bounded(
                client.read_gatt_char(DEVICE_CHALLENGE_UUID),
                self._initialise_timeout,
                "device challenge read",
            )
        )
        if len(challenge) != 16:
            raise AdapterError("device challenge has an invalid length")
        await _bounded(
            client.write_gatt_char(DEVICE_RESPONSE_UUID, challenge, response=True),
            self._initialise_timeout,
            "device response write",
        )

    def _on_disconnect(self, _client: Any) -> None:
        self._client = None
