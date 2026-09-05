import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import cast

from pitboss_admin.events import EventBus, EventType, TelemetryEvent, event_json
from pitboss_admin.models import TelemetrySource

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def event(sequence: int) -> TelemetryEvent:
    return TelemetryEvent(
        type=EventType.PROBE_TEMPERATURE,
        observed_at=NOW,
        sequence=sequence,
        source=TelemetrySource.SIMULATED,
        device_id="safe-device-id",
        probe=1,
        data={"temperatureC": 20.5 + sequence},
    )


def test_canonical_event_aliases_and_compact_json() -> None:
    encoded = event_json(event(1))
    assert '"schemaVersion":1' in encoded
    assert '"deviceId":"safe-device-id"' in encoded
    assert '"observedAt":"2026-09-05T12:00:00Z"' in encoded


def test_event_bus_bounds_history_and_slow_subscriber_queue() -> None:
    async def exercise() -> None:
        bus = EventBus(history_size=2, subscriber_queue_size=1)
        async with bus.subscribe() as queue:
            await bus.publish(event(1))
            await bus.publish(event(2))
            assert (await queue.get()).sequence == 2
        await bus.publish(event(3))
        assert [item.sequence for item in bus.recent()] == [2, 3]

    asyncio.run(exercise())


def test_sse_stream_uses_canonical_event_schema() -> None:
    async def exercise() -> None:
        bus = EventBus()
        stream = cast(AsyncGenerator[str, None], bus.stream())

        async def next_item() -> str:
            return await anext(stream)

        pending = asyncio.create_task(next_item())
        await asyncio.sleep(0)
        await bus.publish(event(4))
        item = await pending
        assert "event: probe.temperature" in item
        assert '"schemaVersion":1' in item
        assert '"temperatureC":24.5' in item
        await stream.aclose()

    asyncio.run(exercise())


def test_event_buffer_sizes_must_be_positive() -> None:
    for arguments in ({"history_size": 0}, {"subscriber_queue_size": 0}):
        try:
            EventBus(
                history_size=arguments.get("history_size", 100),
                subscriber_queue_size=arguments.get("subscriber_queue_size", 100),
            )
        except ValueError as exc:
            assert "positive" in str(exc)
        else:
            raise AssertionError("invalid buffer size was accepted")
