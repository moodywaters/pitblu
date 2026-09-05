import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import pytest

from pitboss_admin.adapters.base import AdapterDisconnectedError, UnsupportedDeviceError
from pitboss_admin.adapters.simulated import SimulatedIGrillAdapter, TemperaturePattern
from pitboss_admin.events import EventBus
from pitboss_admin.models import DiscoveredDevice, TelemetrySource
from pitboss_admin.telemetry import TelemetryState

T = TypeVar("T")


def test_live_clock_handles_delayed_connection_and_stale_recovery() -> None:
    async def exercise() -> None:
        now = datetime(2026, 9, 5, tzinfo=UTC)
        adapter = SimulatedIGrillAdapter(clock=lambda: now)
        now += timedelta(minutes=2)
        await adapter.connect((await adapter.discover(1))[0])
        state = TelemetryState(EventBus())
        try:
            first = await adapter.read_snapshot()
            assert first.observed_at == now
            await state.record("simulated-device", first)
            assert await state.mark_stale(now) == ()
            assert state.probes("simulated-device")[0]["fresh"] is True
            assert all(event.observed_at == now for event in state.events.recent())
            assert all(event.device_id == "simulated-device" for event in state.events.recent())

            adapter.set_stale(True)
            now += timedelta(seconds=16)
            assert await adapter.read_snapshot() is first
            assert await state.mark_stale(now) == ("simulated-device",)
            adapter.set_stale(False)
            second = await adapter.read_snapshot()
            assert second.observed_at == now
            await state.record("simulated-device", second)
            assert await state.mark_stale(now) == ()
            assert state.probes("simulated-device")[0]["fresh"] is True
        finally:
            await state.close()
            await adapter.disconnect()

    asyncio.run(exercise())


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def test_simulator_supports_patterns_presence_battery_stale_and_recovery() -> None:
    adapter = SimulatedIGrillAdapter(4, start_time=datetime(2026, 1, 1, tzinfo=UTC))
    candidate = run(adapter.discover(1))[0]
    run(adapter.connect(candidate))
    adapter.configure_probe(1, pattern=TemperaturePattern.RISING, rate_c_per_read=2)
    adapter.configure_probe(2, pattern=TemperaturePattern.FALLING, rate_c_per_read=1)
    adapter.configure_probe(3, present=False)
    adapter.set_battery_percent(73)

    first = run(adapter.read_snapshot())
    assert first.source is TelemetrySource.SIMULATED
    assert [item.temperature_c for item in first.probes] == [22.0, 20.0, None, 23.0]
    assert first.battery_percent == 73

    adapter.set_stale(True)
    assert run(adapter.read_snapshot()) is first
    adapter.set_stale(False)
    second = run(adapter.read_snapshot())
    assert second.sequence == 2

    adapter.set_connection_available(False)
    with pytest.raises(AdapterDisconnectedError):
        run(adapter.read_snapshot())
    assert run(adapter.discover(1)) == ()
    adapter.set_connection_available(True)
    candidate = run(adapter.discover(1))[0]
    run(adapter.connect(candidate))
    assert run(adapter.read_snapshot()).sequence == 3


def test_simulator_validates_controls_and_disconnects() -> None:
    with pytest.raises(ValueError):
        SimulatedIGrillAdapter(0)
    with pytest.raises(ValueError):
        SimulatedIGrillAdapter(start_time=datetime(2026, 1, 1))

    adapter = SimulatedIGrillAdapter(1)
    with pytest.raises(ValueError):
        run(adapter.discover(0))
    with pytest.raises(AdapterDisconnectedError):
        run(adapter.read_snapshot())
    with pytest.raises(UnsupportedDeviceError):
        run(adapter.connect(DiscoveredDevice("wrong", "wrong", "wrong", None)))
    with pytest.raises(ValueError):
        adapter.configure_probe(2)
    with pytest.raises(ValueError):
        adapter.configure_probe(1, rate_c_per_read=-1)
    with pytest.raises(ValueError):
        adapter.set_battery_percent(101)

    candidate = run(adapter.discover(1))[0]
    run(adapter.connect(candidate))
    assert adapter.is_connected
    run(adapter.disconnect())
    assert not adapter.is_connected
