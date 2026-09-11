from __future__ import annotations

import io
import json
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from pitblu_core.api_client import ApiClient, ApiError


class FakeResponse:
    def __init__(self, data: object, *, status: int = 200, etag: str | None = None) -> None:
        self.status = status
        self._body = json.dumps(data).encode()
        self.headers = Message()
        if etag:
            self.headers["ETag"] = etag

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_client_is_loopback_only_and_sends_auth_and_etag() -> None:
    captured: list[object] = []

    def open_request(request: object, *, timeout: float) -> FakeResponse:
        captured.extend([request, timeout])
        return FakeResponse({"ok": True}, etag='"3"')

    response = ApiClient(port=9090, token="private", opener=open_request).patch(
        "/api/v1/config", {"values": {"mqtt.enabled": True}}, etag='"2"'
    )

    request = captured[0]
    assert isinstance(request, Request)
    assert request.full_url == "http://127.0.0.1:9090/api/v1/config"
    assert request.headers["Authorization"] == "Bearer private"
    assert request.headers["If-match"] == '"2"'
    assert response.etag == '"3"'


def test_health_request_does_not_send_token() -> None:
    requests: list[object] = []

    def open_request(request: object, *, timeout: float) -> FakeResponse:
        requests.append(request)
        return FakeResponse({"status": "ok"})

    ApiClient(token="private", opener=open_request).get("/health", authenticated=False)

    request = requests[0]
    assert isinstance(request, Request)
    assert "Authorization" not in request.headers


def test_http_error_uses_safe_api_envelope() -> None:
    def open_request(_request: object, *, timeout: float) -> FakeResponse:
        payload = {"error": {"code": "not_authenticated", "message": "Token required"}}
        body = io.BytesIO(json.dumps(payload).encode())
        raise HTTPError("local", 401, "unauthorised", Message(), body)

    with pytest.raises(ApiError, match="Token required") as raised:
        ApiClient(opener=open_request).get("/ready")

    assert raised.value.status == 401
    assert raised.value.code == "not_authenticated"


def test_transport_error_does_not_include_request_or_token() -> None:
    def open_request(_request: object, *, timeout: float) -> FakeResponse:
        raise URLError("connection refused")

    with pytest.raises(ApiError, match="local pitblu-core service") as raised:
        ApiClient(token="do-not-print", opener=open_request).get("/api/v1/status")

    assert "do-not-print" not in str(raised.value)


def test_wait_for_operation_polls_to_completion() -> None:
    responses = iter([FakeResponse({"status": "running"}), FakeResponse({"status": "succeeded"})])
    sleeps: list[float] = []
    client = ApiClient(opener=lambda *_args, **_kwargs: next(responses), sleep=sleeps.append)

    response = client.wait_for_operation("op/id", interval=0.25)

    assert response.data["status"] == "succeeded"
    assert sleeps == [0.25]


def test_client_rejects_invalid_ports_and_paths() -> None:
    with pytest.raises(ValueError, match="port"):
        ApiClient(port=0)
    with pytest.raises(ValueError, match="paths"):
        ApiClient().get("health")


def test_operation_timeout_is_bounded() -> None:
    client = ApiClient(opener=lambda *_args, **_kwargs: FakeResponse({"status": "running"}))

    with pytest.raises(ApiError, match="did not finish"):
        client.wait_for_operation("operation", attempts=1)


def test_convenience_methods_use_expected_http_verbs() -> None:
    methods: list[str] = []

    def open_request(request: object, *, timeout: float) -> FakeResponse:
        methods.append(request.get_method())  # type: ignore[attr-defined]
        return FakeResponse({})

    client = ApiClient(opener=open_request)
    client.post("/one", {})
    client.put("/two", {})
    client.delete("/three")

    assert methods == ["POST", "PUT", "DELETE"]


def test_health_wait_retries_until_service_is_ready() -> None:
    responses = iter([FakeResponse({"status": "starting"}), FakeResponse({"status": "ok"})])
    sleeps: list[float] = []
    client = ApiClient(opener=lambda *_args, **_kwargs: next(responses), sleep=sleeps.append)

    assert client.wait_for_health(interval=0.1).data == {"status": "ok"}
    assert sleeps == [0.1]
