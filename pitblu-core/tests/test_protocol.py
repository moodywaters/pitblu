import pytest

from pitblu_core.protocol import (
    UNPLUGGED_PROBE,
    ProtocolError,
    TemperatureUnit,
    decode_battery_percent,
    decode_probe_temperature_c,
    decode_temperature_unit,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (bytes.fromhex("1900"), 25.0),
        (bytes.fromhex("140080"), 20.0),
        (UNPLUGGED_PROBE.to_bytes(2, "little") + b"\x80", None),
    ],
)
def test_decode_probe_temperature(payload: bytes, expected: float | None) -> None:
    assert decode_probe_temperature_c(payload) == expected


@pytest.mark.parametrize("payload", [b"", b"\x01"])
def test_decode_probe_temperature_rejects_wrong_length(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        decode_probe_temperature_c(payload)


def test_decode_temperature_unit() -> None:
    assert decode_temperature_unit(b"\x00") is TemperatureUnit.FAHRENHEIT
    assert decode_temperature_unit(b"\x01") is TemperatureUnit.CELSIUS
    assert decode_temperature_unit(b"\x01\x00") is None


@pytest.mark.parametrize("payload", [b"", b"\x02"])
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
