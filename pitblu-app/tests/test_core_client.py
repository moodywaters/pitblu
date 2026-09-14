import asyncio
from typing import Any

from pitblu_app.core_client import PitbluCoreClient


class FakeResponse:
    def __init__(self, data: Any = None, lines: list[str] | None = None) -> None:
        self.data = data
        self.lines = lines or []

    def json(self) -> Any:
        return self.data

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):  # type: ignore[no-untyped-def]
        for line in self.lines:
            yield line


class StreamContext:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeClient:
    def __init__(self, responses: dict[str, Any], calls: list[str]) -> None:
        self.responses = responses
        self.calls = calls

    async def __aenter__(self):  # type: ignore[no-untyped-def]
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, url: str) -> FakeResponse:
        self.calls.append(url)
        return FakeResponse(self.responses[url])

    def stream(self, method: str, url: str) -> StreamContext:
        self.calls.append(f"{method} {url}")
        return StreamContext(FakeResponse(lines=self.responses[url]))


def factory(responses: dict[str, Any], calls: list[str]):  # type: ignore[no-untyped-def]
    def create(**_kwargs: object) -> FakeClient:
        return FakeClient(responses, calls)

    return create


def test_reconcile_collects_each_devices_probe_and_battery_state():
    base = "http://core"
    calls: list[str] = []
    responses = {
        f"{base}/api/v1/devices": [{"deviceId": "a"}, {"deviceId": "b"}],
        f"{base}/api/v1/devices/a": {"deviceId": "a", "name": "First"},
        f"{base}/api/v1/devices/a/probes": [{"probe": 1, "temperatureC": 20}],
        f"{base}/api/v1/devices/a/battery": {"percentage": 90},
        f"{base}/api/v1/devices/b": {"deviceId": "b", "name": "Second"},
        f"{base}/api/v1/devices/b/probes": [{"probe": 1, "temperatureC": 30}],
        f"{base}/api/v1/devices/b/battery": {"percentage": 80},
    }
    client = PitbluCoreClient(base, "secret", client_factory=factory(responses, calls))
    devices = asyncio.run(client.reconcile())
    assert [(item["deviceId"], item["probes"][0]["probe"]) for item in devices] == [
        ("a", 1),
        ("b", 1),
    ]
    assert len(calls) == 7


def test_event_stream_parses_core_sse_data_frames():
    base = "http://core"
    calls: list[str] = []
    responses = {
        f"{base}/api/v1/events/stream": [
            "event: probe.temperature",
            'data: {"type":"probe.temperature","deviceId":"a","probe":1}',
        ]
    }
    client = PitbluCoreClient(base, client_factory=factory(responses, calls))

    async def first_event():  # type: ignore[no-untyped-def]
        stream = client.events()
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    assert asyncio.run(first_event()) == {
        "type": "probe.temperature",
        "deviceId": "a",
        "probe": 1,
    }
    assert calls == [f"GET {base}/api/v1/events/stream"]
