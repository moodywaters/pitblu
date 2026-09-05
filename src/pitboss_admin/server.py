"""Close SSE responses before Uvicorn waits for HTTP request drainage."""

import socket

import uvicorn

from pitboss_admin.events import EventBus


class GracefulServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, events: EventBus) -> None:
        super().__init__(config)
        self.events = events

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        self.events.close_streams()
        await super().shutdown(sockets=sockets)
