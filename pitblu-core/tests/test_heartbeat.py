import asyncio
from datetime import timedelta

from pitblu_core.events import EventBus, EventType
from pitblu_core.models import DeviceSnapshot, ProbeReading, TelemetrySource, utc_now
from pitblu_core.telemetry import TelemetryState


def _snapshot(*, communication: bool, present: bool = True) -> DeviceSnapshot:
    observed_at = utc_now()
    probe = ProbeReading(
        1,
        communication,
        present if communication else False,
        20.0 if communication and present else None,
        observed_at,
        1,
        TelemetrySource.PHYSICAL,
        None if communication else "read_failed",
    )
    return DeviceSnapshot(
        "igrill-v202",
        (probe,),
        None,
        False,
        observed_at,
        1,
        TelemetrySource.PHYSICAL,
        successful_communication_at=observed_at if communication else None,
    )


def test_heartbeat_requires_explicit_success_and_ages_without_reconnecting() -> None:
    async def exercise() -> None:
        bus = EventBus()
        state = TelemetryState(bus, heartbeat_stale_after=0.01)
        await state.register_heartbeat("device", TelemetrySource.PHYSICAL)
        assert state.heartbeat("device", desired_state="connected")["status"] == "unknown"

        await state.record("device", _snapshot(communication=False))
        unknown_events = [
            event for event in bus.recent() if event.type is EventType.THERMOMETER_HEARTBEAT
        ]
        assert len(unknown_events) == 1

        successful = _snapshot(communication=True, present=False)
        await state.record("device", successful)
        heartbeat = state.heartbeat("device", desired_state="connected")
        assert heartbeat["status"] == "healthy"
        assert heartbeat["fresh"] is True
        assert heartbeat["source"] == "physical"
        assert heartbeat["lastSuccessfulCommunicationAt"] == (
            successful.successful_communication_at.isoformat()  # type: ignore[union-attr]
        )

        await asyncio.sleep(0.02)
        heartbeat = state.heartbeat("device", desired_state="connected")
        assert heartbeat["status"] == "stale"
        assert heartbeat["fresh"] is False
        assert [
            event.data["status"]
            for event in bus.recent()
            if event.type is EventType.THERMOMETER_HEARTBEAT
        ] == ["unknown", "healthy", "stale"]
        assert not any(event.type is EventType.OPERATION for event in bus.recent())
        await state.close()

    asyncio.run(exercise())


def test_heartbeat_sequence_disconnect_and_session_reset() -> None:
    async def exercise() -> None:
        first_bus = EventBus()
        state = TelemetryState(first_bus)
        await state.register_heartbeat("device", TelemetrySource.SIMULATED)
        at = utc_now()
        await state.communication_succeeded("device", at, TelemetrySource.SIMULATED)
        await state.communication_succeeded(
            "device", at - timedelta(seconds=1), TelemetrySource.SIMULATED
        )
        healthy = state.heartbeat("device", desired_state="connected")
        assert healthy["sequence"] == 2
        await state.heartbeat_disconnected("device")
        disconnected = state.heartbeat("device", desired_state="disconnected")
        assert disconnected["status"] == "disconnected"
        assert disconnected["lastSuccessfulCommunicationAt"] == at.isoformat()
        assert disconnected["sequence"] == 3
        resumed = state.heartbeat("device", desired_state="connected")
        assert resumed["status"] == "stale"
        await state.heartbeat_expected("device")
        resumed = state.heartbeat("device", desired_state="connected")
        assert resumed["status"] == "stale"
        assert resumed["sequence"] == 4
        await state.close()

        second_bus = EventBus()
        restarted = TelemetryState(second_bus)
        await restarted.register_heartbeat("device", TelemetrySource.SIMULATED)
        unknown = restarted.heartbeat("device", desired_state="connected")
        assert unknown["status"] == "unknown"
        assert unknown["lastSuccessfulCommunicationAt"] is None
        assert unknown["sessionId"] != healthy["sessionId"]
        try:
            restarted.heartbeat("missing", desired_state="connected")
        except KeyError:
            pass
        else:
            raise AssertionError("missing heartbeat did not fail")
        await restarted.close()

    asyncio.run(exercise())
