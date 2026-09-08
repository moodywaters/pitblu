"""Canonical device-adapter models shared by physical and simulated devices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class TelemetrySource(StrEnum):
    PHYSICAL = "physical"
    SIMULATED = "simulated"


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """Supported discovery result with an opaque, process-local connection handle."""

    discovery_id: str
    name: str
    model: str
    rssi: int | None
    _native: object = field(repr=False, compare=False, default=None)
    _identity: str | None = field(repr=False, compare=False, default=None)


@dataclass(frozen=True, slots=True)
class ProbeReading:
    number: int
    available: bool
    present: bool
    temperature_c: float | None
    observed_at: datetime
    sequence: int
    source: TelemetrySource
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.number <= 4:
            raise ValueError("probe number must be between 1 and 4")
        if self.observed_at.tzinfo is None:
            raise ValueError("probe observation time must be timezone-aware")
        if self.sequence < 1:
            raise ValueError("probe sequence must be positive")
        if self.temperature_c is not None and (not self.available or not self.present):
            raise ValueError("a temperature requires an available, present probe")


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    model: str
    probes: tuple[ProbeReading, ...]
    battery_percent: int | None
    battery_available: bool
    observed_at: datetime
    sequence: int
    source: TelemetrySource
    battery_observed_at: datetime | None = None

    def __post_init__(self) -> None:
        numbers = [probe.number for probe in self.probes]
        if len(numbers) not in range(1, 5) or len(set(numbers)) != len(numbers):
            raise ValueError("a snapshot requires one to four unique probes")
        if self.observed_at.tzinfo is None:
            raise ValueError("snapshot observation time must be timezone-aware")
        if self.sequence < 1:
            raise ValueError("snapshot sequence must be positive")
        if self.battery_percent is not None and not 0 <= self.battery_percent <= 100:
            raise ValueError("battery percentage must be between 0 and 100")
        if self.battery_percent is not None and not self.battery_available:
            raise ValueError("a battery value requires battery availability")
        if self.battery_observed_at is not None and self.battery_observed_at.tzinfo is None:
            raise ValueError("battery observation time must be timezone-aware")
