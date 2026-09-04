import asyncio
import json
import sys
from typing import Any, ClassVar

import pytest
from bleak import BleakScanner

import pitboss_admin.ble_spike as spike
from pitboss_admin.ble_spike import ProofError, authenticate, redact_private_values
from pitboss_admin.protocol import (
    APP_CHALLENGE,
    APP_CHALLENGE_UUID,
    BATTERY_LEVEL_UUID,
    DEVICE_CHALLENGE_UUID,
    DEVICE_RESPONSE_UUID,
    PROBE_TEMPERATURE_UUIDS,
    TEMPERATURE_UNIT_UUID,
    UNPLUGGED_PROBE,
    V202_TEMPERATURE_SERVICE_UUID,
)


class FakeClient:
    def __init__(self, challenge: bytes = bytes(range(16))) -> None:
        self.challenge = challenge
        self.calls: list[tuple[Any, ...]] = []

    async def write_gatt_char(self, uuid: str, payload: bytes, *, response: bool) -> None:
        self.calls.append(("write", uuid, payload, response))

    async def read_gatt_char(self, uuid: str) -> bytes:
        self.calls.append(("read", uuid))
        return self.challenge


def test_authentication_loops_device_challenge_back() -> None:
    client = FakeClient()

    asyncio.run(authenticate(client, timeout=1))

    assert client.calls == [
        ("write", APP_CHALLENGE_UUID, APP_CHALLENGE, True),
        ("read", DEVICE_CHALLENGE_UUID),
        ("write", DEVICE_RESPONSE_UUID, bytes(range(16)), True),
    ]


def test_authentication_rejects_wrong_challenge_length() -> None:
    with pytest.raises(ProofError, match="16 bytes"):
        asyncio.run(authenticate(FakeClient(b"short"), timeout=1))


def test_redaction_removes_bluetooth_addresses() -> None:
    address = ":".join(["AA", "bb", "01", "23", "45", "67"])
    message = f"failed for {address} but not iGrill_V202-CD09"
    assert redact_private_values(message) == (
        "failed for [bluetooth-address-redacted] but not iGrill_V202-CD09"
    )


class FakeService:
    uuid = V202_TEMPERATURE_SERVICE_UUID


class FakeProofClient:
    services: ClassVar[list[FakeService]] = [FakeService()]

    def __init__(self, _device: object, *, timeout: float, pair: bool) -> None:
        self.timeout = timeout
        self.pair = pair
        self.is_connected = False

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def write_gatt_char(self, _uuid: str, _payload: bytes, *, response: bool) -> None:
        assert response

    async def read_gatt_char(self, uuid: str) -> bytes:
        values = {
            DEVICE_CHALLENGE_UUID: bytes(range(16)),
            TEMPERATURE_UNIT_UUID: b"\x01",
            BATTERY_LEVEL_UUID: b"\x4b",
            PROBE_TEMPERATURE_UUIDS[0]: b"\x19\x00",
            PROBE_TEMPERATURE_UUIDS[2]: UNPLUGGED_PROBE.to_bytes(2, "little"),
            PROBE_TEMPERATURE_UUIDS[3]: UNPLUGGED_PROBE.to_bytes(2, "little"),
        }
        if uuid == PROBE_TEMPERATURE_UUIDS[1]:
            address = ":".join(["AA", "BB", "CC", "DD", "EE", "FF"])
            raise RuntimeError(f"read failed for {address}")
        return values[uuid]


async def _find_device(*_args: object, **_kwargs: object) -> object:
    return object()


def test_run_proof_returns_sanitised_physical_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BleakScanner, "find_device_by_filter", _find_device)
    monkeypatch.setattr(spike, "BleakClient", FakeProofClient)

    result = asyncio.run(spike.run_proof())

    assert result["batteryPercent"] == 75
    assert result["bluetoothAddressIncluded"] is False
    probes = result["probes"]
    assert isinstance(probes, list)
    assert probes[0]["temperatureC"] == 25.0
    assert probes[1]["diagnostic"] == "RuntimeError"
    assert probes[2]["present"] is False


def test_run_proof_rejects_missing_device(monkeypatch: pytest.MonkeyPatch) -> None:
    async def find_none(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(BleakScanner, "find_device_by_filter", find_none)
    with pytest.raises(ProofError, match="was not discovered"):
        asyncio.run(spike.run_proof())


def test_run_proof_rejects_wrong_model(monkeypatch: pytest.MonkeyPatch) -> None:
    class WrongModelClient(FakeProofClient):
        services: ClassVar[list[FakeService]] = []

    monkeypatch.setattr(BleakScanner, "find_device_by_filter", _find_device)
    monkeypatch.setattr(spike, "BleakClient", WrongModelClient)
    with pytest.raises(ProofError, match="V202 temperature service"):
        asyncio.run(spike.run_proof())


def test_main_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def successful(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"source": "physical"}

    monkeypatch.setattr(spike, "run_proof", successful)
    monkeypatch.setattr(sys, "argv", ["pitboss-ble-proof"])
    assert spike.main() == 0
    assert json.loads(capsys.readouterr().out) == {"source": "physical"}


def test_main_redacts_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    address = ":".join(["AA", "BB", "CC", "DD", "EE", "FF"])

    async def failing(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ProofError(f"failed for {address}")

    monkeypatch.setattr(spike, "run_proof", failing)
    monkeypatch.setattr(sys, "argv", ["pitboss-ble-proof"])
    assert spike.main() == 1
    captured = capsys.readouterr()
    assert address not in captured.err
    assert "[bluetooth-address-redacted]" in captured.err
