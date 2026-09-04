import pytest

from pitboss_admin.protocol import (
    UNPLUGGED_PROBE,
    ProtocolError,
    TemperatureUnit,
    decode_battery_percent,
    decode_probe_temperature_c,
    decode_temperature_unit,
)


@pytest.mark.parametrize(
    ("payload", "unit", "expected"),
    [
        (bytes.fromhex("1900"), TemperatureUnit.CELSIUS, 25.0),
        (bytes.fromhex("4d00"), TemperatureUnit.FAHRENHEIT, 25.0),
        (UNPLUGGED_PROBE.to_bytes(2, "little"), TemperatureUnit.CELSIUS, None),
    ],
)
def test_decode_probe_temperature(
    payload: bytes, unit: TemperatureUnit, expected: float | None
) -> None:
    assert decode_probe_temperature_c(payload, unit) == expected


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x01\x02\x03"])
def test_decode_probe_temperature_rejects_wrong_length(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_probe_temperature_c(payload, TemperatureUnit.CELSIUS)


def test_decode_temperature_unit() -> None:
    assert decode_temperature_unit(b"\x00") is TemperatureUnit.FAHRENHEIT
    assert decode_temperature_unit(b"\x01") is TemperatureUnit.CELSIUS


@pytest.mark.parametrize("payload", [b"", b"\x02", b"\x00\x01"])
def test_decode_temperature_unit_rejects_invalid_payload(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_temperature_unit(payload)


def test_decode_battery_percent() -> None:
    assert decode_battery_percent(b"\x00") == 0
    assert decode_battery_percent(b"\x64") == 100


@pytest.mark.parametrize("payload", [b"", b"\x65", b"\x32\x00"])
def test_decode_battery_rejects_invalid_payload(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_battery_percent(payload)
