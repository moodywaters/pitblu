from datetime import UTC, datetime

import pytest

from pitboss_admin.models import DeviceSnapshot, ProbeReading, TelemetrySource

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def probe(number: int, *, present: bool = True, temperature: float | None = 20.0) -> ProbeReading:
    return ProbeReading(
        number=number,
        available=True,
        present=present,
        temperature_c=temperature,
        observed_at=NOW,
        sequence=1,
        source=TelemetrySource.PHYSICAL,
    )


def test_probe_requires_valid_number_and_consistent_temperature() -> None:
    with pytest.raises(ValueError, match="between 1 and 4"):
        probe(0)
    with pytest.raises(ValueError, match="requires"):
        ProbeReading(1, False, False, 20.0, NOW, 1, TelemetrySource.PHYSICAL)
    with pytest.raises(ValueError, match="timezone-aware"):
        ProbeReading(1, True, True, 20.0, datetime(2026, 9, 4), 1, TelemetrySource.PHYSICAL)
    with pytest.raises(ValueError, match="positive"):
        ProbeReading(1, True, True, 20.0, NOW, 0, TelemetrySource.PHYSICAL)


def test_snapshot_validates_probes_and_battery() -> None:
    snapshot = DeviceSnapshot(
        "igrill-v202", (probe(1), probe(2)), 60, True, NOW, 1, TelemetrySource.PHYSICAL
    )
    assert snapshot.battery_percent == 60

    with pytest.raises(ValueError, match="unique probes"):
        DeviceSnapshot(
            "igrill-v202", (probe(1), probe(1)), 60, True, NOW, 1, TelemetrySource.PHYSICAL
        )
    with pytest.raises(ValueError, match="between 0 and 100"):
        DeviceSnapshot("igrill-v202", (probe(1),), 101, True, NOW, 1, TelemetrySource.PHYSICAL)
    with pytest.raises(ValueError, match="availability"):
        DeviceSnapshot("igrill-v202", (probe(1),), 60, False, NOW, 1, TelemetrySource.PHYSICAL)
    with pytest.raises(ValueError, match="timezone-aware"):
        DeviceSnapshot(
            "igrill-v202",
            (probe(1),),
            60,
            True,
            datetime(2026, 9, 4),
            1,
            TelemetrySource.PHYSICAL,
        )
    with pytest.raises(ValueError, match="positive"):
        DeviceSnapshot("igrill-v202", (probe(1),), 60, True, NOW, 0, TelemetrySource.PHYSICAL)
