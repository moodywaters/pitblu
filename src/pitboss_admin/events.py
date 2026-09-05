"""Canonical internal events and bounded asynchronous fan-out."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from pitboss_admin.models import TelemetrySource, utc_now


class EventType(StrEnum):
    SERVICE_AVAILABILITY = "service.availability"
    DEVICE_AVAILABILITY = "device.availability"
    DEVICE_CONNECTION = "device.connection"
    BATTERY = "device.battery"
    PROBE_AVAILABILITY = "probe.availability"
    PROBE_TEMPERATURE = "probe.temperature"
    OPERATION = "operation.state"
    CONFIGURATION = "configuration.changed"


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[1] = Field(1, alias="schemaVersion")
    event_id: str = Field(default_factory=lambda: uuid4().hex, alias="eventId")
    session_id: str = Field("", alias="sessionId")
    type: EventType
    observed_at: datetime = Field(default_factory=utc_now, alias="observedAt")
    sequence: int = Field(ge=1)
    source: TelemetrySource
    device_id: str | None = Field(None, alias="deviceId")
    probe: int | None = Field(None, ge=1, le=4)
    data: dict[str, Any]


class EventBus:
    def __init__(
        self,
        *,
        history_size: int = 100,
        subscriber_queue_size: int = 100,
        persist: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if min(history_size, subscriber_queue_size) < 1:
            raise ValueError("event buffer sizes must be positive")
        self._history: deque[TelemetryEvent] = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[TelemetryEvent]] = set()
        self._subscriber_queue_size = subscriber_queue_size
        self.session_id = uuid4().hex
        self._persist = persist
        self._latest: dict[tuple[str | None, EventType, int | None], TelemetryEvent] = {}

    async def publish(self, event: TelemetryEvent) -> None:
        event = event.model_copy(update={"session_id": self.session_id})
        if event.type in {EventType.OPERATION, EventType.CONFIGURATION}:
            if self._persist is not None:
                self._persist(event.model_dump(mode="json", by_alias=True))
        elif event.type is not EventType.PROBE_TEMPERATURE:
            self._latest[(event.device_id, event.type, event.probe)] = event
        self._history.append(event)
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def recent(self) -> list[TelemetryEvent]:
        return list(self._history)

    def retained_state(self) -> list[TelemetryEvent]:
        return list(self._latest.values())

    def forget_device(self, device_id: str) -> None:
        self._latest = {key: event for key, event in self._latest.items() if key[0] != device_id}

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[TelemetryEvent]]:
        queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(self._subscriber_queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def stream(self, *, heartbeat: float = 60) -> AsyncIterator[str]:
        async with self.subscribe() as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                payload = event.model_dump_json(by_alias=True)
                yield f"id: {event.event_id}\nevent: {event.type.value}\ndata: {payload}\n\n"


def event_json(event: TelemetryEvent) -> str:
    return json.dumps(event.model_dump(mode="json", by_alias=True), separators=(",", ":"))
