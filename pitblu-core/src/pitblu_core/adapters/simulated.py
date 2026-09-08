"""Deterministic simulated iGrill adapter using the production adapter models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pitblu_core.adapters.base import AdapterDisconnectedError, UnsupportedDeviceError
from pitblu_core.models import DeviceSnapshot, DiscoveredDevice, ProbeReading, TelemetrySource


class TemperaturePattern(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"


@dataclass(slots=True)
class _SimulatedProbe:
    present: bool
    temperature_c: float
    pattern: TemperaturePattern
    rate_c_per_read: float


class SimulatedIGrillAdapter:
    def __init__(
        self,
        probe_count: int = 4,
        *,
        start_time: datetime | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 1 <= probe_count <= 4:
            raise ValueError("simulator probe count must be between 1 and 4")
        self._probe_count = probe_count
        self._probes = [
            _SimulatedProbe(True, 20.0 + number, TemperaturePattern.STABLE, 1.0)
            for number in range(probe_count)
        ]
        self._battery_percent = 100
        self._connected = False
        self._connection_available = True
        self._stale = False
        self._sequence = 0
        self._clock = clock
        self._time = start_time or datetime(2026, 1, 1, tzinfo=UTC)
        if self._time.tzinfo is None:
            raise ValueError("simulator start time must be timezone-aware")
        self._time = self._time.astimezone(UTC)
        self._last_snapshot: DeviceSnapshot | None = None
        self._candidate = DiscoveredDevice(
            discovery_id="simulated-igrill-v202",
            name="Simulated iGrill V202",
            model="igrill-v202",
            rssi=-42,
            _identity="simulated-igrill-v202",
        )

    @property
    def source(self) -> TelemetrySource:
        return TelemetrySource.SIMULATED

    @property
    def is_connected(self) -> bool:
        return self._connected and self._connection_available

    async def discover(self, duration: float) -> tuple[DiscoveredDevice, ...]:
        if duration <= 0:
            raise ValueError("scan duration must be positive")
        return (self._candidate,) if self._connection_available else ()

    async def recover_registered(self, identity: str) -> bool:
        return False

    async def connect(self, device: DiscoveredDevice) -> None:
        if device.discovery_id != self._candidate.discovery_id:
            raise UnsupportedDeviceError("unknown simulated device")
        if not self._connection_available:
            raise AdapterDisconnectedError("simulated connection loss is active")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def read_snapshot(self) -> DeviceSnapshot:
        if not self.is_connected:
            raise AdapterDisconnectedError("simulated iGrill is not connected")
        if self._stale and self._last_snapshot is not None:
            return self._last_snapshot

        self._sequence += 1
        self._time = self._clock() if self._clock is not None else self._time + timedelta(seconds=5)
        readings: list[ProbeReading] = []
        for number, probe in enumerate(self._probes, start=1):
            if probe.pattern is TemperaturePattern.RISING:
                probe.temperature_c += probe.rate_c_per_read
            elif probe.pattern is TemperaturePattern.FALLING:
                probe.temperature_c -= probe.rate_c_per_read
            readings.append(
                ProbeReading(
                    number=number,
                    available=True,
                    present=probe.present,
                    temperature_c=round(probe.temperature_c, 1) if probe.present else None,
                    observed_at=self._time,
                    sequence=self._sequence,
                    source=self.source,
                )
            )
        snapshot = DeviceSnapshot(
            model="igrill-v202",
            probes=tuple(readings),
            battery_percent=self._battery_percent,
            battery_available=True,
            observed_at=self._time,
            sequence=self._sequence,
            source=self.source,
        )
        self._last_snapshot = snapshot
        return snapshot

    def configure_probe(
        self,
        number: int,
        *,
        present: bool | None = None,
        temperature_c: float | None = None,
        pattern: TemperaturePattern | None = None,
        rate_c_per_read: float | None = None,
    ) -> None:
        probe = self._get_probe(number)
        if present is not None:
            probe.present = present
        if temperature_c is not None:
            probe.temperature_c = temperature_c
        if pattern is not None:
            probe.pattern = pattern
        if rate_c_per_read is not None:
            if rate_c_per_read < 0:
                raise ValueError("probe rate must not be negative")
            probe.rate_c_per_read = rate_c_per_read

    def set_battery_percent(self, value: int) -> None:
        if not 0 <= value <= 100:
            raise ValueError("battery percentage must be between 0 and 100")
        self._battery_percent = value

    def set_connection_available(self, available: bool) -> None:
        self._connection_available = available
        if not available:
            self._connected = False

    def set_stale(self, stale: bool) -> None:
        self._stale = stale

    def _get_probe(self, number: int) -> _SimulatedProbe:
        if not 1 <= number <= self._probe_count:
            raise ValueError("probe number is outside the simulated range")
        return self._probes[number - 1]
