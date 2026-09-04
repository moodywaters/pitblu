# Physical acceptance

Status: passed for v0.1.0

## Preconditions

- Target Raspberry Pi environment matches the project plan.
- The iGrill advertises as `iGrill_V202-CD09`.
- At least one probe is inserted and its display value is noted.
- The official Weber application is fully closed.
- No Bluetooth address, LAN address, token or broker secret is captured.

## Procedure

The operator and Codex use one Raspberry Pi command at a time. The repository is transferred or
checked out, an isolated Python 3.13 environment is created, dependencies are installed, tests are
run, and then `pitboss-ble-proof` is executed. Each step waits for the preceding output.

## Pass record

Do not mark this document passed until the output shows:

- `source` equal to `physical`;
- model `igrill-v202`;
- successful zero-challenge loopback authentication;
- a battery percentage from 0 through 100;
- at least one present probe with `temperatureC` matching the display within 1 degree Celsius;
- `bluetoothAddressIncluded` equal to `false`.

Raw payload bytes may be retained as sanitised protocol evidence. Bluetooth addresses must not be
retained. After validation, record the date, target software versions, redacted output and manual
display comparison here.

## v0.1.0 result

- Date: 4 September 2026
- Host: Raspberry Pi 4 Model B Rev 1.4
- OS: Raspberry Pi OS on Debian 13.5 Trixie, 64-bit ARM
- Python: 3.13.5
- BlueZ: 5.82, as confirmed in the authoritative environment record
- Advertised name: `iGrill_V202-CD09`
- Discovery: succeeded within the configured 20-second scan
- Pairing: accepted once through the Raspberry Pi desktop pairing agent and retained by BlueZ
- Connection: succeeded with a 60-second diagnostic allowance
- Initialisation: zero-challenge loopback succeeded
- Display comparison: two connected probes each showed 20°C; decoded probes 1 and 2 each read
  20.0°C
- Battery: 60 per cent
- Privacy: success output stated `bluetoothAddressIncluded: false`; no address was retained
- Target test result: 20 tests passed with 93 per cent coverage on Python 3.13.5 after the final
  decoder changes were covered by the same hardware-independent suite on Windows

Sanitised protocol evidence:

```json
{
  "authentication": "zero-challenge-loopback-succeeded",
  "batteryPercent": 60,
  "batteryRawPayloadHex": "3c",
  "bluetoothAddressIncluded": false,
  "deviceName": "iGrill_V202-CD09",
  "model": "igrill-v202",
  "probes": [
    {"probe": 1, "present": true, "rawPayloadHex": "140080", "temperatureC": 20.0},
    {"probe": 2, "present": true, "rawPayloadHex": "140080", "temperatureC": 20.0},
    {"probe": 3, "present": false, "rawPayloadHex": "30f880", "temperatureC": null},
    {"probe": 4, "present": false, "rawPayloadHex": "30f880", "temperatureC": null}
  ],
  "reportedTemperatureUnit": "undetermined",
  "source": "physical",
  "temperatureUnitRawPayloadHex": "000a000002"
}
```

Two inserted physical probes appeared correctly on logical probes 1 and 2, both at 20°C. Logical
probes 3 and 4 returned the unplugged sentinel. The five-byte unit metadata remains uninterpreted;
raw V202 probe values were proven directly against the Celsius display.
