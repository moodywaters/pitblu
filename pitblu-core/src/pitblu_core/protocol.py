"""Small, hardware-independent subset of the Weber iGrill BLE protocol."""

from __future__ import annotations

from enum import IntEnum

AUTHENTICATION_SERVICE_UUID = "64ac0000-4a4b-4b58-9f37-94d3c52ffdf7"
APP_CHALLENGE_UUID = "64ac0002-4a4b-4b58-9f37-94d3c52ffdf7"
DEVICE_CHALLENGE_UUID = "64ac0003-4a4b-4b58-9f37-94d3c52ffdf7"
DEVICE_RESPONSE_UUID = "64ac0004-4a4b-4b58-9f37-94d3c52ffdf7"

V202_TEMPERATURE_SERVICE_UUID = "ada7590f-2e6d-469e-8f7b-1822b386a5e9"
TEMPERATURE_UNIT_UUID = "06ef0001-2e06-4b79-9e33-fce2c42805ec"
PROBE_TEMPERATURE_UUIDS = (
    "06ef0002-2e06-4b79-9e33-fce2c42805ec",
    "06ef0004-2e06-4b79-9e33-fce2c42805ec",
    "06ef0006-2e06-4b79-9e33-fce2c42805ec",
    "06ef0008-2e06-4b79-9e33-fce2c42805ec",
)

BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
UNPLUGGED_PROBE = 63_536
APP_CHALLENGE = bytes(16)


class ProtocolError(ValueError):
    """A characteristic payload does not match the understood protocol."""


class TemperatureUnit(IntEnum):
    """Values reported by the iGrill temperature-unit characteristic."""

    FAHRENHEIT = 0
    CELSIUS = 1


def decode_temperature_unit(payload: bytes | bytearray) -> TemperatureUnit | None:
    """Decode a documented one-byte display unit, or decline extended metadata."""
    if not payload:
        raise ProtocolError("temperature unit payload must contain at least one byte")
    if len(payload) != 1:
        return None
    try:
        return TemperatureUnit(payload[0])
    except ValueError as exc:
        raise ProtocolError("temperature unit is not recognised") from exc


def decode_probe_temperature_c(payload: bytes | bytearray) -> float | None:
    """Decode the leading 16-bit raw Celsius probe value."""
    if len(payload) < 2:
        raise ProtocolError("probe payload must contain at least two bytes")
    raw = int.from_bytes(payload[:2], byteorder="little", signed=False)
    if raw == UNPLUGGED_PROBE:
        return None
    return float(raw)


def decode_battery_percent(payload: bytes | bytearray) -> int:
    """Decode and validate the standard Bluetooth battery percentage."""
    if len(payload) != 1:
        raise ProtocolError("battery payload must contain exactly one byte")
    value = payload[0]
    if value > 100:
        raise ProtocolError("battery percentage is outside 0 to 100")
    return value
