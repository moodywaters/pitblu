import asyncio
from typing import Any

import pytest
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from pitboss_admin.api import ThrottledError, create_app
from pitboss_admin.configuration import ConfigurationManager
from pitboss_admin.security import RateLimit, RequestBounds
from pitboss_admin.storage import AdministrativeStore


def test_rate_limit_refills_on_controlled_time() -> None:
    ticks = [0.0]
    limiter = RateLimit(30, clock=lambda: ticks[0])
    assert [limiter.retry_after() for _ in range(10)] == [0] * 10
    assert limiter.retry_after() == 2
    ticks[0] = 2
    assert limiter.retry_after() == 0
    ticks[0] = 100
    assert limiter.retry_after() == 0


def test_request_bounds_cover_chunked_payload_without_content_length() -> None:
    async def exercise() -> None:
        called = False
        output: list[Any] = []
        chunks = iter(
            [
                {"type": "http.request", "body": b"1234", "more_body": True},
                {"type": "http.request", "body": b"5678", "more_body": False},
            ]
        )

        async def receive() -> Any:
            return next(chunks)

        async def send(message: Any) -> None:
            output.append(message)

        async def app(*args: Any) -> None:
            nonlocal called
            called = True

        await RequestBounds(app, maximum_bytes=5)({"type": "http", "method": "POST"}, receive, send)
        assert not called
        assert output[0]["status"] == 413
        assert b"1234" not in output[1]["body"]

    asyncio.run(exercise())


def test_api_limits_and_safe_correlation() -> None:
    store = AdministrativeStore()
    configuration = ConfigurationManager(
        store,
        environ={
            "PITBOSS_SECURITY__MUTATIONS_PER_MINUTE": "1",
        },
    )
    app = create_app(store=store, configuration=configuration)
    with TestClient(app) as api:
        rejected = api.put("/api/v1/config/secrets/mqtt.password", content=b"x" * 20000)
        assert rejected.status_code == 413
        first = api.post("/api/v1/config/validate", json={"values": {}})
        assert first.status_code == 200
        rejected = api.post("/api/v1/config/validate", json={"values": {}})
        assert rejected.status_code == 429
        assert int(rejected.headers["retry-after"]) > 0
        assert rejected.json()["error"]["code"] == "rate_limited"
        result = api.get("/health", headers={"X-Correlation-ID": "private:" + "x" * 100})
        assert "private" not in result.headers["x-correlation-id"]
        assert result.headers["cache-control"] == "no-store"
    store.close()


def test_auth_attempts_are_bounded_and_public_health_remains_available() -> None:
    store = AdministrativeStore()
    app = create_app(
        store=store,
        configuration=ConfigurationManager(
            store,
            environ={
                "PITBOSS_AUTH__MODE": "token",
                "PITBOSS_SECURITY__AUTH_REQUESTS_PER_MINUTE": "10",
            },
        ),
    )
    with TestClient(app) as api:
        for _ in range(10):
            assert api.get("/api/v1/status").status_code == 401
        assert api.get("/api/v1/status").status_code == 429
        assert api.get("/health").status_code == 200
    store.close()


def test_sse_capacity_released_even_if_response_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        store = AdministrativeStore()
        app = create_app(
            store=store,
            configuration=ConfigurationManager(
                store, environ={"PITBOSS_SECURITY__MAXIMUM_SSE_CLIENTS": "1"}
            ),
        )
        endpoint = next(
            route.endpoint
            for route in app.routes
            if isinstance(route, APIRoute) and route.path == "/api/v1/events/stream"
        )

        async def cancelled(*args: Any) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(StreamingResponse, "__call__", cancelled)
        response = await endpoint(None)
        with pytest.raises(ThrottledError):
            await endpoint(None)
        with pytest.raises(asyncio.CancelledError):
            await response({}, None, None)
        response = await endpoint(None)
        with pytest.raises(asyncio.CancelledError):
            await response({}, None, None)
        store.close()

    asyncio.run(exercise())
