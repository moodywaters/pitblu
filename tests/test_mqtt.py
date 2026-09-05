import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import pytest

from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import TelemetrySource
from pitboss_admin.mqtt import MqttPublisher, MqttSettings, mqtt_payload, retained, topic_for

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def event(event_type: EventType, *, probe: int | None = None) -> TelemetryEvent:
    data: dict[str, object] = {"temperatureC": 21.5} if probe else {"available": True}
    return TelemetryEvent(
        type=event_type,
        observed_at=NOW,
        sequence=9,
        source=TelemetrySource.SIMULATED,
        device_id=None if event_type is EventType.SERVICE_AVAILABILITY else "device-1",
        probe=probe,
        data=data,
    )


def test_topic_payload_and_retain_contract() -> None:
    assert topic_for("/custom/", event(EventType.SERVICE_AVAILABILITY)) == (
        "custom/v1/service/availability"
    )
    assert topic_for("pitboss", event(EventType.DEVICE_AVAILABILITY)).endswith(
        "/device-1/availability"
    )
    assert topic_for("pitboss", event(EventType.DEVICE_CONNECTION)).endswith("/device-1/connection")
    assert topic_for("pitboss", event(EventType.BATTERY)).endswith("/device-1/battery")
    availability = event(EventType.PROBE_AVAILABILITY, probe=2)
    temperature = event(EventType.PROBE_TEMPERATURE, probe=2)
    assert topic_for("pitboss", availability).endswith("/probes/2/availability")
    assert topic_for("pitboss", temperature).endswith("/probes/2/temperature")
    payload = json.loads(mqtt_payload(temperature))
    assert payload == {
        "schemaVersion": 1,
        "observedAt": "2026-09-05T12:00:00+00:00",
        "sequence": 9,
        "source": "simulated",
        "deviceId": "device-1",
        "probe": 2,
        "temperatureC": 21.5,
    }
    assert retained(availability.type)
    assert not retained(EventType.PROBE_TEMPERATURE)


def test_topic_validation() -> None:
    missing_device = event(EventType.SERVICE_AVAILABILITY).model_copy(
        update={"type": EventType.BATTERY}
    )
    with pytest.raises(ValueError, match="device identifier"):
        topic_for("pitboss", missing_device)
    with pytest.raises(ValueError, match="probe number"):
        topic_for("pitboss", event(EventType.PROBE_TEMPERATURE))


class FakeClient:
    def __init__(self, entered: asyncio.Event, **options: Any) -> None:
        self.entered = entered
        self.options = options
        self.publications: list[tuple[str, str, int, bool]] = []

    async def __aenter__(self) -> "FakeClient":
        self.entered.set()
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> None:
        self.publications.append((topic, payload, qos, retain))


def test_publisher_sets_last_will_and_publishes_online_event_and_offline() -> None:
    async def exercise() -> None:
        entered = asyncio.Event()
        clients: list[FakeClient] = []

        def factory(host: str, port: int, **options: Any) -> FakeClient:
            assert (host, port) == ("broker", 1883)
            result = FakeClient(entered, **options)
            clients.append(result)
            return result

        settings = MqttSettings(host="broker", base_topic="cook", source=TelemetrySource.SIMULATED)
        publisher = MqttPublisher(settings, client_factory=factory)
        bus = EventBus()
        task = asyncio.create_task(publisher.run(bus))
        await entered.wait()
        await asyncio.sleep(0)
        await bus.publish(event(EventType.PROBE_TEMPERATURE, probe=1))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        client = clients[0]
        will = client.options["will"]
        assert will.topic == "cook/v1/service/availability"
        assert will.qos == 1 and will.retain is True
        assert json.loads(will.payload)["source"] == "simulated"
        assert [publication[0] for publication in client.publications] == [
            "cook/v1/service/availability",
            "cook/v1/devices/device-1/probes/1/temperature",
            "cook/v1/service/availability",
        ]
        assert json.loads(client.publications[0][1])["available"] is True
        assert client.publications[1][2:] == (1, False)
        assert json.loads(client.publications[-1][1])["available"] is False

    asyncio.run(exercise())
