"""Loopback-only standard-library client for the pitblu-core administration API."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """Decoded API response and concurrency metadata."""

    status: int
    data: Any
    etag: str | None = None


class ApiError(RuntimeError):
    """A deliberately secret-free API or transport failure."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class ApiClient:
    """Call only the service bound to this machine's IPv4 loopback interface."""

    def __init__(
        self,
        *,
        port: int = 8080,
        token: str | None = None,
        timeout: float = 10.0,
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        self._base_url = f"http://127.0.0.1:{port}"
        self._token = token
        self._timeout = timeout
        self._opener = opener
        self._sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        authenticated: bool = True,
        etag: str | None = None,
    ) -> ApiResponse:
        if not path.startswith("/"):
            raise ValueError("API paths must start with '/'")
        headers = {"Accept": "application/json"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if authenticated and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if etag is not None:
            headers["If-Match"] = etag
        request = Request(self._base_url + path, data=payload, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read()
                data: Any = json.loads(raw) if raw else None
                return ApiResponse(response.status, data, response.headers.get("ETag"))
        except HTTPError as exc:
            raise self._http_error(exc) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", None)
            message = "The local pitblu-core service could not be reached"
            if isinstance(reason, str) and reason:
                message = f"{message}: {reason}"
            raise ApiError(message) from None

    def get(self, path: str, *, authenticated: bool = True) -> ApiResponse:
        return self.request("GET", path, authenticated=authenticated)

    def post(self, path: str, body: Mapping[str, Any] | None = None) -> ApiResponse:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: Mapping[str, Any], *, etag: str | None = None) -> ApiResponse:
        return self.request("PATCH", path, body=body, etag=etag)

    def put(self, path: str, body: Mapping[str, Any]) -> ApiResponse:
        return self.request("PUT", path, body=body)

    def delete(self, path: str) -> ApiResponse:
        return self.request("DELETE", path)

    def device_path(self, device_id: str, suffix: str = "") -> str:
        return f"/api/v1/devices/{quote(device_id, safe='')}{suffix}"

    def wait_for_operation(
        self, operation_id: str, *, attempts: int = 30, interval: float = 1.0
    ) -> ApiResponse:
        path = f"/api/v1/operations/{quote(operation_id, safe='')}"
        for attempt in range(attempts):
            response = self.get(path)
            state = response.data.get("status") if isinstance(response.data, dict) else None
            if state in {"succeeded", "failed", "cancelled"}:
                return response
            if attempt + 1 < attempts:
                self._sleep(interval)
        raise ApiError("The local operation did not finish before the timeout")

    @staticmethod
    def _http_error(exc: HTTPError) -> ApiError:
        code = None
        message = f"The local service returned HTTP {exc.code}"
        try:
            body = json.loads(exc.read())
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                candidate_code = error.get("code")
                candidate_message = error.get("message")
                if isinstance(candidate_code, str):
                    code = candidate_code
                if isinstance(candidate_message, str):
                    message = candidate_message
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            pass
        return ApiError(message, status=exc.code, code=code)
