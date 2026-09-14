from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from pitblue_app.models import utc_now


class ApplicationEvents:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    async def publish(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {
            "eventId": uuid4().hex,
            "type": event_type,
            "occurredAt": utc_now().isoformat(),
            "data": data,
        }
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        return event

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(100)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def stream(
        self, predicate: Callable[[dict[str, Any]], bool] | None = None
    ) -> AsyncIterator[str]:
        async with self.subscribe() as queue:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), 30)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if predicate is not None and not predicate(event):
                    continue
                payload = json.dumps(event, separators=(",", ":"))
                yield f"id: {event['eventId']}\nevent: {event['type']}\ndata: {payload}\n\n"
