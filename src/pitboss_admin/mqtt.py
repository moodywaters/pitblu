"""MQTT v1 topic mapping and asyncio-safe publisher."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

import aiomqtt

from pitboss_admin.connection import BackoffPolicy
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
    heartbeat: float = 60
    stable_after: float = 60
    timeout: float = 10


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
    if event.session_id:
        payload["sessionId"] = event.session_id
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
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
        backoff: BackoffPolicy | None = None,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory
        self._sleep = sleep
        self._clock = clock
        self._backoff = backoff or BackoffPolicy()
        self.state = "starting"
        self.failures = 0
        self.error_code: str | None = None
        self.retry_in: float | None = None
        self._session_id = ""
        self._connected_at: float | None = None

    def status(self) -> dict[str, object]:
        return {
            "state": self.state,
            "failures": self.failures,
            "errorCode": self.error_code,
            "retryIn": self.retry_in,
        }

    async def publish_event(self, client: Any, event: TelemetryEvent) -> None:
        if event.type in {EventType.OPERATION, EventType.CONFIGURATION}:
            return
        await client.publish(
            topic_for(self.settings.base_topic, event),
            mqtt_payload(event),
            qos=self.settings.qos,
            retain=retained(event.type),
        )

    async def run(self, events: EventBus) -> None:
        self._session_id = events.session_id
        try:
            while True:
                self._connected_at = None
                try:
                    self.state = "connecting"
                    await self._connected_run(events)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.failures += 1
                    self.error_code = "mqtt_connection_failed"
                    logging.getLogger(__name__).warning('{"event":"mqtt_connection_failed"}')
                    self.state = "backoff"
                    if (
                        self._connected_at is not None
                        and self._clock() - self._connected_at >= self.settings.stable_after
                    ):
                        self._backoff.reset()
                    self.retry_in = self._backoff.next_delay()
                    await self._sleep(self.retry_in)
        finally:
            self.state = "stopped"
            self.retry_in = None

    async def _connected_run(self, events: EventBus) -> None:
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
            timeout=self.settings.timeout,
        )
        async with client:
            self._connected_at = self._clock()
            self.state = "connected"
            self.error_code = None
            self.retry_in = None
            available = self._service_payload(True, sequence=1)
            try:
                async with events.subscribe() as queue:
                    await client.publish(
                        availability_topic, available, qos=self.settings.qos, retain=True
                    )
                    for event in events.retained_state():
                        if event.type is not EventType.SERVICE_AVAILABILITY:
                            await self.publish_event(client, event)
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), self.settings.heartbeat)
                        except TimeoutError:
                            await client.publish(
                                availability_topic,
                                self._service_payload(True, sequence=1),
                                qos=self.settings.qos,
                                retain=True,
                            )
                        else:
                            if (
                                event.type is EventType.SERVICE_AVAILABILITY
                                and event.data.get("available") is False
                            ):
                                for current in events.retained_state():
                                    if current.type is not EventType.SERVICE_AVAILABILITY:
                                        await self.publish_event(client, current)
                                return
                            await self.publish_event(client, event)
            finally:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(
                        client.publish(
                            availability_topic,
                            self._service_payload(False, sequence=2),
                            qos=self.settings.qos,
                            retain=True,
                        ),
                        timeout=self.settings.timeout,
                    )

    def _service_payload(self, available: bool, *, sequence: int) -> str:
        return json.dumps(
            {
                "schemaVersion": 1,
                "available": available,
                "observedAt": utc_now().isoformat(),
                "sequence": sequence,
                "source": self.settings.source.value,
                "sessionId": self._session_id,
            },
            separators=(",", ":"),
        )
