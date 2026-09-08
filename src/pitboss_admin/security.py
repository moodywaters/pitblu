"""Bounded request intake and process-wide throttling for the trusted-LAN API."""

import asyncio
import math
from collections.abc import Callable
from time import monotonic
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RateLimit:
    def __init__(self, per_minute: int, *, clock: Callable[[], float] = monotonic) -> None:
        self._rate = per_minute / 60
        self._capacity = min(per_minute, 10)
        self._tokens = float(self._capacity)
        self._clock = clock
        self._last = clock()

    def retry_after(self) -> int:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + max(0, now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return 0
        return max(1, math.ceil((1 - self._tokens) / self._rate))


class RequestBounds:
    def __init__(self, app: ASGIApp, *, maximum_bytes: int) -> None:
        self.app = app
        self.maximum_bytes = maximum_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > self.maximum_bytes:
                        await self._reject(scope, receive, send, 413, "request_too_large")
                        return
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await self._reject(scope, receive, send, 408, "request_timeout")
            return
        body = b"".join(chunks)
        delivered = False

        async def buffered() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, buffered, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, status: int, code: str) -> None:
        correlation = scope.get("state", {}).get("correlation_id") or uuid4().hex
        response = JSONResponse(
            {"error": {"code": code, "message": "request rejected", "correlationId": correlation}},
            status_code=status,
            headers={"X-Correlation-ID": correlation, "Cache-Control": "no-store"},
        )
        await response(scope, receive, send)
