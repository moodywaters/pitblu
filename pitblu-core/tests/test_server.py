import asyncio
import socket

import pytest
import uvicorn
from fastapi import FastAPI
from starlette.responses import StreamingResponse

from pitblu_core.events import EventBus
from pitblu_core.server import GracefulServer


def test_shutdown_drains_active_sse_without_cancellation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        events = EventBus()
        app = FastAPI()

        @app.get("/events")
        async def stream() -> StreamingResponse:
            return StreamingResponse(events.stream(), media_type="text/event-stream")

        server = GracefulServer(
            uvicorn.Config(app, access_log=False, timeout_graceful_shutdown=1), events
        )
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            task = asyncio.create_task(server.serve(sockets=[listener]))
            try:
                async with asyncio.timeout(5):
                    while not server.started:
                        await asyncio.sleep(0.01)
                    reader, writer = await asyncio.open_connection(
                        "127.0.0.1", listener.getsockname()[1]
                    )
                    try:
                        writer.write(b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n")
                        await writer.drain()
                        headers = await reader.readuntil(b"\r\n\r\n")
                        assert b"200 OK" in headers
                        server.should_exit = True
                        body = await reader.read()
                        assert body.endswith(b"0\r\n\r\n")
                        await task
                    finally:
                        writer.close()
                        await writer.wait_closed()
            finally:
                server.should_exit = True
                await asyncio.wait_for(task, 5)
        assert "timeout graceful shutdown exceeded" not in caplog.text

    asyncio.run(exercise())
