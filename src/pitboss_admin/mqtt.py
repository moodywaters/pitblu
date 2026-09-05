"""MQTT v1 topic mapping and asyncio-safe publisher."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any

import aiomqtt

from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import TelemetrySource, utc_now


@dataclass(frozen=True, slots=True)
class MqttSettings:
    host: str = "127.0.0.1"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    tls: bool = False
    base_topic: str = "pitboss"
    qos: int = 1
    source: TelemetrySource = TelemetrySource.PHYSICAL


_TOPIC_PARTS = {
    EventType.DEVICE_AVAILABILITY: "availability",
    EventType.DEVICE_CONNECTION: "connection",
    EventType.BATTERY: "battery",
}


def topic_for(base_topic: str, event: TelemetryEvent) -> str:
    base = base_topic.strip("/")
    if event.type is EventType.SERVICE_AVAILABILITY:
        return f"{base}/v1/service/availability"
    if event.device_id is None:
        raise ValueError("device event requires a device identifier")
    if event.type in _TOPIC_PARTS:
        return f"{base}/v1/devices/{event.device_id}/{_TOPIC_PARTS[event.type]}"
    if event.probe is None:
        raise ValueError("probe event requires a probe number")
    leaf = "availability" if event.type is EventType.PROBE_AVAILABILITY else "temperature"
    return f"{base}/v1/devices/{event.device_id}/probes/{event.probe}/{leaf}"


def mqtt_payload(event: TelemetryEvent) -> str:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "observedAt": event.observed_at.isoformat(),
        "sequence": event.sequence,
        "source": event.source.value,
    }
    if event.device_id is not None:
        payload["deviceId"] = event.device_id
    if event.probe is not None:
        payload["probe"] = event.probe
    payload.update(event.data)
    return json.dumps(payload, separators=(",", ":"))


def retained(event_type: EventType) -> bool:
    return event_type is not EventType.PROBE_TEMPERATURE


class MqttPublisher:
    def __init__(
        self,
        settings: MqttSettings,
        *,
        client_factory: Any = aiomqtt.Client,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory

    async def publish_event(self, client: Any, event: TelemetryEvent) -> None:
        await client.publish(
            topic_for(self.settings.base_topic, event),
            mqtt_payload(event),
            qos=self.settings.qos,
            retain=retained(event.type),
        )

    async def run(self, events: EventBus) -> None:
        availability_topic = f"{self.settings.base_topic.strip('/')}/v1/service/availability"
        unavailable = self._service_payload(False, sequence=2)
        will = aiomqtt.Will(availability_topic, unavailable, qos=self.settings.qos, retain=True)
        tls_context = ssl.create_default_context() if self.settings.tls else None
        client = self._client_factory(
            self.settings.host,
            self.settings.port,
            username=self.settings.username,
            password=self.settings.password,
            will=will,
            tls_context=tls_context,
        )
        async with client:
            available = self._service_payload(True, sequence=1)
            await client.publish(availability_topic, available, qos=self.settings.qos, retain=True)
            try:
                async with events.subscribe() as queue:
                    while True:
                        await self.publish_event(client, await queue.get())
            finally:
                await client.publish(
                    availability_topic, unavailable, qos=self.settings.qos, retain=True
                )

    def _service_payload(self, available: bool, *, sequence: int) -> str:
        return json.dumps(
            {
                "schemaVersion": 1,
                "available": available,
                "observedAt": utc_now().isoformat(),
                "sequence": sequence,
                "source": self.settings.source.value,
            },
            separators=(",", ":"),
        )
