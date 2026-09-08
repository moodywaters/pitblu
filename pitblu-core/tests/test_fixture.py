import json
from pathlib import Path

from pitblu_core.protocol import decode_battery_percent, decode_probe_temperature_c


def test_sanitised_physical_fixture_replays_v202_payloads() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "v202" / "physical-proof.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["containsBluetoothAddress"] is False
    assert decode_battery_percent(bytes.fromhex(fixture["battery"])) == 60
    readings = [decode_probe_temperature_c(bytes.fromhex(value)) for value in fixture["probes"]]
    assert readings == [20.0, 20.0, None, None]
