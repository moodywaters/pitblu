import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar, TypeVar, cast

import pytest

from pitboss_admin.adapters.base import (
    AdapterDisconnectedError,
    AdapterError,
    UnsupportedDeviceError,
)
from pitboss_admin.adapters.igrill_v202 import BleakIGrillV202Adapter, _bounded
from pitboss_admin.models import DiscoveredDevice, TelemetrySource
from pitboss_admin.protocol import (
    APP_CHALLENGE,
    APP_CHALLENGE_UUID,
    BATTERY_LEVEL_UUID,
    DEVICE_CHALLENGE_UUID,
    DEVICE_RESPONSE_UUID,
    PROBE_TEMPERATURE_UUIDS,
    UNPLUGGED_PROBE,
    V202_TEMPERATURE_SERVICE_UUID,
)

T = TypeVar("T")


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


class Native:
    def __init__(self, name: str) -> None:
        self.name = name
        self.address = ":".join(["AA", "BB", "CC", "DD", "EE", "FF"])


class Advertisement:
    def __init__(self, local_name: str | None, service_uuids: list[str], rssi: int = -50) -> None:
        self.local_name = local_name
        self.service_uuids = service_uuids
        self.rssi = rssi


class Scanner:
    results: ClassVar[dict[str, tuple[Native, Advertisement]]] = {}

    @classmethod
    async def discover(cls, *, timeout: float, return_adv: bool) -> object:
        assert timeout > 0
        assert return_adv
        return cls.results


class Service:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class Client:
    instances: ClassVar[list["Client"]] = []
    service_uuid: ClassVar[str] = V202_TEMPERATURE_SERVICE_UUID
    challenge: ClassVar[bytes] = bytes(range(16))

    def __init__(self, _native: object, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.is_connected = False
        self.services = [Service(self.service_uuid)]
        self.writes: list[tuple[str, bytes, bool]] = []
        self.callback = kwargs["disconnected_callback"]
        assert callable(self.callback)
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def write_gatt_char(self, uuid: str, payload: bytes, *, response: bool) -> None:
        self.writes.append((uuid, payload, response))

    async def read_gatt_char(self, uuid: str) -> bytes:
        values = {
            DEVICE_CHALLENGE_UUID: self.challenge,
            BATTERY_LEVEL_UUID: b"\x3c",
            PROBE_TEMPERATURE_UUIDS[0]: bytes.fromhex("140080"),
            PROBE_TEMPERATURE_UUIDS[1]: bytes.fromhex("150080"),
            PROBE_TEMPERATURE_UUIDS[2]: UNPLUGGED_PROBE.to_bytes(2, "little") + b"\x80",
            PROBE_TEMPERATURE_UUIDS[3]: b"x",
        }
        return values[uuid]


def adapter() -> BleakIGrillV202Adapter:
    Client.instances.clear()
    Scanner.results = {
        "supported": (
            Native("iGrill_V202-TEST"),
            Advertisement("iGrill_V202-TEST", []),
        ),
        "service-match": (
            Native("Unknown"),
            Advertisement(None, [V202_TEMPERATURE_SERVICE_UUID.upper()], -60),
        ),
        "unrelated": (Native("Headphones"), Advertisement("Headphones", [])),
    }
    return BleakIGrillV202Adapter(scanner=Scanner, client_factory=Client)


def test_physical_adapter_discovers_connects_reads_and_disconnects() -> None:
    subject = adapter()
    discovered = run(subject.discover(1))
    assert len(discovered) == 2
    assert discovered[0].name == "iGrill_V202-TEST"
    assert discovered[1].name == "Unknown"
    assert "AA:BB" not in repr(discovered[0])
    assert subject.source is TelemetrySource.PHYSICAL

    run(subject.connect(discovered[0]))
    assert subject.is_connected
    client = Client.instances[0]
    assert client.kwargs["pair"] is True
    assert client.writes == [
        (APP_CHALLENGE_UUID, APP_CHALLENGE, True),
        (DEVICE_RESPONSE_UUID, bytes(range(16)), True),
    ]
    run(subject.connect(discovered[0]))
    assert len(Client.instances) == 1

    first = run(subject.read_snapshot())
    assert first.sequence == 1
    assert first.battery_percent == 60
    assert [probe.temperature_c for probe in first.probes] == [20.0, 21.0, None, None]
    assert [probe.available for probe in first.probes] == [True, True, True, False]
    assert first.probes[3].error_code == "ProtocolError"
    assert all(probe.source is TelemetrySource.PHYSICAL for probe in first.probes)
    assert run(subject.read_snapshot()).sequence == 2

    run(subject.disconnect())
    assert not subject.is_connected
    run(subject.disconnect())


def test_adapter_rejects_unknown_or_wrong_model_candidates() -> None:
    subject = adapter()
    with pytest.raises(UnsupportedDeviceError):
        run(subject.connect(DiscoveredDevice("missing", "Unknown", "igrill-v202", None)))
    discovered = run(subject.discover(1))[0]
    wrong = DiscoveredDevice(discovered.discovery_id, discovered.name, "other", None)
    with pytest.raises(UnsupportedDeviceError):
        run(subject.connect(wrong))


def test_adapter_rejects_wrong_service_and_invalid_challenge() -> None:
    class WrongServiceClient(Client):
        service_uuid = "not-v202"

    subject = adapter()
    subject._client_factory = WrongServiceClient
    with pytest.raises(UnsupportedDeviceError, match="does not expose"):
        run(subject.connect(run(subject.discover(1))[0]))
    assert not WrongServiceClient.instances[-1].is_connected

    class BadChallengeClient(Client):
        challenge = b"short"

    subject = adapter()
    subject._client_factory = BadChallengeClient
    with pytest.raises(AdapterError, match="invalid length"):
        run(subject.connect(run(subject.discover(1))[0]))


def test_adapter_handles_battery_failure_and_disconnect_callback() -> None:
    class BatteryFailureClient(Client):
        async def read_gatt_char(self, uuid: str) -> bytes:
            if uuid == BATTERY_LEVEL_UUID:
                raise RuntimeError("battery unavailable")
            return await super().read_gatt_char(uuid)

    subject = adapter()
    subject._client_factory = BatteryFailureClient
    candidate = run(subject.discover(1))[0]
    run(subject.connect(candidate))
    snapshot = run(subject.read_snapshot())
    assert not snapshot.battery_available
    assert snapshot.battery_percent is None
    client = BatteryFailureClient.instances[-1]
    callback = cast("Callable[[object], None]", client.callback)
    callback(client)
    assert not subject.is_connected
    with pytest.raises(AdapterDisconnectedError):
        run(subject.read_snapshot())


def test_adapter_and_timeout_validation() -> None:
    subject = adapter()
    with pytest.raises(ValueError, match="positive"):
        BleakIGrillV202Adapter(connect_timeout=0)
    with pytest.raises(ValueError, match="positive"):
        run(subject.discover(0))

    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(AdapterError, match="timed out"):
        run(_bounded(slow(), 0.001, "test operation"))
