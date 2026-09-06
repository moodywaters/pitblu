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

## v0.2.0 production-adapter gate

Status: passed

Run `pitboss-v202-check` from the installed v0.2.0 branch on the target Raspberry Pi with the
official Weber application closed. A pass requires physical source, polling connection state,
battery availability, four logical probe results, both attached probes within 1°C of the display,
the two unattached channels absent, and `bluetoothAddressIncluded` equal to `false`.

The command must complete or fail within its explicit deadlines and disconnect before exit. Record
only its sanitised JSON and the manual display comparison. Do not record a Bluetooth address.

### v0.2.0 result

- Date: 4 September 2026
- Command: `pitboss-v202-check` using a 60-second diagnostic connection allowance and 15-second
  read allowance
- Connection state: `polling`
- Source and model: `physical`, `igrill-v202`
- Probe 1: present and available, 19.0°C, matching the displayed 19°C
- Probe 2: present and available, 21.0°C, matching the displayed 21°C
- Probes 3 and 4: available characteristics reporting no inserted probe
- Battery: available, 60 per cent
- Privacy: output stated `bluetoothAddressIncluded: false`; no address was retained
- Target checks: 47 tests passed with 94.03 per cent coverage on Python 3.13.5; Ruff lint and
  formatting checks passed; strict mypy checking passed for 21 source files

The command completed normally and disconnected before exit. All v0.2.0 acceptance criteria were
met on the target Raspberry Pi.

## v0.3.0 Raspberry Pi API gate

Status: passed

On 4 September 2026, the v0.3.0 candidate ran natively on the target Raspberry Pi using its
simulated adapter and loopback-only API default. The following were demonstrated through REST:

- unauthenticated minimal `GET /health` returned `{"status":"ok"}`;
- `POST /api/v1/scans` returned a queued operation and its resource progressed to `succeeded`;
- the scan returned one supported simulated V202 without a Bluetooth address;
- registration with initial connection returned HTTP 201 plus a queued operation;
- the connection operation progressed to `succeeded`;
- the probe resource returned four available, present readings at 20.0°C through 23.0°C, all with
  `source` equal to `simulated`;
- the battery resource returned 100 per cent with `source` equal to `simulated`;
- the temporary API process stopped normally after the checks.

The target quality gate passed 58 tests with 93.28 per cent coverage on Python 3.13.5. Ruff lint
and format checks passed, and strict mypy reported no issues in 30 source files. No private address,
LAN address or secret was recorded.

## v0.4.0 Raspberry Pi telemetry gate

On 5 September 2026, the corrected candidate demonstrated the following using the simulator,
the loopback API and the existing authenticated Mosquitto broker:

- SSE delivered four probe readings with stable device identifiers, shared observation timestamps,
  increasing sequences and an explicit simulated source.
- Reconnection restored fresh readings; sequence 23 advanced to 27 over 20 seconds.
- After disconnect, REST reported stale probe and battery state with unavailable numeric values.
- Service availability arrived as retained JSON at QoS 1.
- Four MQTT temperatures arrived at 20, 21, 22 and 23 degrees Celsius with the specified payload
  fields, QoS 1 and no retain flag.
- A new subscriber after disconnect received four retained stale probe-availability messages and
  no temperature messages.
- Force-stopping the isolated test API caused the broker to publish retained service
  unavailability at QoS 1, proving Last Will behaviour.

Live validation identified and corrected event-field alias handling and simulator timestamp drift
after delayed connection. Regression tests now cover both cases. A stored credential mismatch
was resolved by verifying authentication before saving and comparing the stored value locally;
no credential was recorded in this evidence.

The final corrected Pi candidate passed 71 tests at 93.26 per cent coverage on Python 3.13.5.
Ruff lint and formatting passed for 61 files; strict mypy passed for 37 source files.
The corrected candidate also passed 71 tests at 93.26 per cent locally. These telemetry checks use simulated devices;
earlier milestones separately established physical V202 probe and battery readings.

The test API is stopped following the Last Will test. The Will observation timestamp is its
preparation time at connection setup, not the time the broker detects a lost connection.

## v1.0.0 extended soak gate

On 6 September 2026 the user confirmed a minimum 16-hour physical soak for v1.0.0,
superseding the original 12-hour requirement to cover cooks lasting 14 hours or longer.
Run it after native deployment and targeted recovery checks. Record reading freshness,
MQTT reception, interruptions and automatic recovery throughout. Completion requires no
manual intervention and review of any telemetry gaps. This gate is pending, not a prerequisite
for completing earlier v0.x milestones. Short recovery tests remain required for v0.5.0.
