"""Focused physical BLE proof for the Weber iGrill V202."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
import sys
from collections.abc import Awaitable
from typing import Any, TypeVar

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from pitboss_admin.protocol import (
    APP_CHALLENGE,
    APP_CHALLENGE_UUID,
    BATTERY_LEVEL_UUID,
    DEVICE_CHALLENGE_UUID,
    DEVICE_RESPONSE_UUID,
    PROBE_TEMPERATURE_UUIDS,
    TEMPERATURE_UNIT_UUID,
    V202_TEMPERATURE_SERVICE_UUID,
    decode_battery_percent,
    decode_probe_temperature_c,
    decode_temperature_unit,
)

DEFAULT_DEVICE_NAME = "iGrill_V202-CD09"
_BLUETOOTH_ADDRESS = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
_T = TypeVar("_T")


class ProofError(RuntimeError):
    """The physical proof could not be completed safely."""


def redact_private_values(message: str) -> str:
    """Remove conventional Bluetooth addresses from diagnostic text."""
    return _BLUETOOTH_ADDRESS.sub("[bluetooth-address-redacted]", message)


async def _with_timeout(awaitable: Awaitable[_T], seconds: float, operation: str) -> _T:
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except TimeoutError as exc:
        raise ProofError(f"{operation} timed out after {seconds:g} seconds") from exc


def _matches_name(device: BLEDevice, advertisement: AdvertisementData, expected_name: str) -> bool:
    return expected_name in {device.name, advertisement.local_name}


async def authenticate(client: Any, timeout: float) -> None:
    """Perform the iGrill zero-challenge and encrypted loopback handshake."""
    await _with_timeout(
        client.write_gatt_char(APP_CHALLENGE_UUID, APP_CHALLENGE, response=True),
        timeout,
        "application challenge write",
    )
    challenge = bytes(
        await _with_timeout(
            client.read_gatt_char(DEVICE_CHALLENGE_UUID),
            timeout,
            "device challenge read",
        )
    )
    if len(challenge) != 16:
        raise ProofError("device challenge did not contain 16 bytes")
    await _with_timeout(
        client.write_gatt_char(DEVICE_RESPONSE_UUID, challenge, response=True),
        timeout,
        "device response write",
    )


async def run_proof(
    device_name: str = DEFAULT_DEVICE_NAME,
    scan_timeout: float = 20.0,
    connect_timeout: float = 10.0,
    read_timeout: float = 5.0,
) -> dict[str, object]:
    """Discover one named V202 and return sanitised physical readings."""
    print(f"Scanning for {device_name!r}...", file=sys.stderr)
    device = await BleakScanner.find_device_by_filter(
        lambda found, advert: _matches_name(found, advert, device_name),
        timeout=scan_timeout,
    )
    if device is None:
        raise ProofError(f"device {device_name!r} was not discovered")

    print("Device discovered; connecting and initialising...", file=sys.stderr)
    client = BleakClient(device, timeout=connect_timeout, pair=True)
    try:
        await _with_timeout(
            client.connect(),
            connect_timeout,
            "BLE connection and GATT service resolution",
        )
        service_uuids = {service.uuid.lower() for service in client.services}
        if V202_TEMPERATURE_SERVICE_UUID not in service_uuids:
            raise ProofError("connected device does not expose the V202 temperature service")

        await authenticate(client, read_timeout)
        unit_payload = bytes(
            await _with_timeout(
                client.read_gatt_char(TEMPERATURE_UNIT_UUID),
                read_timeout,
                "temperature unit read",
            )
        )
        unit = decode_temperature_unit(unit_payload)
        battery_payload = bytes(
            await _with_timeout(
                client.read_gatt_char(BATTERY_LEVEL_UUID), read_timeout, "battery read"
            )
        )

        probes: list[dict[str, object]] = []
        for number, uuid in enumerate(PROBE_TEMPERATURE_UUIDS, start=1):
            try:
                payload = bytes(
                    await _with_timeout(
                        client.read_gatt_char(uuid), read_timeout, f"probe {number} read"
                    )
                )
                temperature_c = decode_probe_temperature_c(payload, unit)
            except Exception as exc:
                probes.append(
                    {
                        "probe": number,
                        "present": False,
                        "temperatureC": None,
                        "diagnostic": redact_private_values(type(exc).__name__),
                    }
                )
            else:
                probes.append(
                    {
                        "probe": number,
                        "present": temperature_c is not None,
                        "temperatureC": temperature_c,
                        "rawPayloadHex": payload.hex(),
                    }
                )
    finally:
        if client.is_connected:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), timeout=5.0)

    if not any(probe["present"] for probe in probes):
        raise ProofError("no inserted probe produced a valid temperature")

    return {
        "proofVersion": 1,
        "source": "physical",
        "deviceName": device_name,
        "model": "igrill-v202",
        "authentication": "zero-challenge-loopback-succeeded",
        "reportedTemperatureUnit": unit.name.lower(),
        "batteryPercent": decode_battery_percent(battery_payload),
        "batteryRawPayloadHex": battery_payload.hex(),
        "probes": probes,
        "bluetoothAddressIncluded": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_DEVICE_NAME, help="exact advertised name")
    parser.add_argument("--scan-timeout", type=float, default=20.0)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--read-timeout", type=float, default=5.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = asyncio.run(
            run_proof(args.name, args.scan_timeout, args.connect_timeout, args.read_timeout)
        )
    except KeyboardInterrupt:
        print("Physical proof interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        message = redact_private_values(str(exc)) or type(exc).__name__
        print(f"Physical proof failed: {message}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
