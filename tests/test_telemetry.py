import asyncio
from datetime import UTC, datetime, timedelta

from pitboss_admin.events import EventBus, EventType
from pitboss_admin.models import DeviceSnapshot, ProbeReading, TelemetrySource
from pitboss_admin.telemetry import TelemetryState

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def snapshot() -> DeviceSnapshot:
    probes = (
        ProbeReading(1, True, True, 20.0, NOW, 7, TelemetrySource.PHYSICAL),
        ProbeReading(2, True, False, None, NOW, 7, TelemetrySource.PHYSICAL),
    )
    return DeviceSnapshot("igrill-v202", probes, 60, True, NOW, 7, TelemetrySource.PHYSICAL)


def test_telemetry_record_views_events_stale_transition_and_removal() -> None:
    async def exercise() -> None:
        bus = EventBus(history_size=30)
        state = TelemetryState(bus, stale_after=15)
        await state.record("device-1", snapshot())
        assert state.probes("device-1")[0]["temperatureC"] == 20.0
        assert state.probes("device-1")[0]["fresh"] is True
        assert state.battery("device-1")["percentage"] == 60  # type: ignore[index]
        initial_types = [item.type for item in bus.recent()]
        assert all(item.device_id == "device-1" for item in bus.recent())
        assert all(item.observed_at == NOW for item in bus.recent())
        assert initial_types == [
            EventType.DEVICE_AVAILABILITY,
            EventType.DEVICE_CONNECTION,
            EventType.BATTERY,
            EventType.PROBE_AVAILABILITY,
            EventType.PROBE_TEMPERATURE,
            EventType.PROBE_AVAILABILITY,
        ]

        assert await state.mark_stale(NOW + timedelta(seconds=14)) == ()
        assert await state.mark_stale(NOW + timedelta(seconds=15)) == ("device-1",)
        assert await state.mark_stale(NOW + timedelta(seconds=30)) == ()
        availability = [item for item in bus.recent() if item.type is EventType.DEVICE_AVAILABILITY]
        assert [item.sequence for item in availability] == [7, 8]
        stale_probe = state.probes("device-1")[0]
        assert stale_probe["available"] is False
        assert stale_probe["temperatureC"] is None
        assert stale_probe["errorCode"] == "stale"
        assert state.battery("device-1")["fresh"] is False  # type: ignore[index]

        await state.connection("device-1", "disconnected")
        assert bus.recent()[-1].data == {"available": False, "reason": "disconnected"}
        await state.remove("device-1")
        assert state.probes("device-1") == []
        assert state.battery("device-1") is None
        await state.connection("device-1", "polling")
        await state.close()

    asyncio.run(exercise())


def test_stale_threshold_must_be_positive() -> None:
    try:
        TelemetryState(EventBus(), stale_after=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("invalid stale threshold was accepted")
