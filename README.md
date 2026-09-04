# pitboss-admin

`pitboss-admin` is a planned headless, API-first Raspberry Pi gateway for Weber iGrill
thermometers. Development is deliberately gated. Version 0.2.0 builds a tested device foundation
on the physical BLE protocol proven in version 0.1.0.

The REST service, MQTT, persistence and native service deployment belong to later milestones and
are not implemented yet.

## v0.1.0 result

Version 0.1.0 passed its Raspberry Pi physical gate on 4 September 2026, demonstrating:

- discovery of the expected advertised name within 20 seconds;
- connection and Weber challenge/response initialisation;
- at least one inserted probe temperature, normalised to Celsius;
- the standard Bluetooth battery percentage;
- output containing no Bluetooth address.

See [physical acceptance](docs/physical-acceptance.md) for the sanitised evidence. Later milestones
remain unimplemented.

## v0.2.0 device foundation

- A production Bleak adapter discovers, connects, authenticates and reads all four V202 channels.
- Physical and simulated devices implement the same asynchronous adapter boundary.
- Discovery remains active through scheduled scans without keeping the radio continuously busy.
- Desired and observed connection state are modelled explicitly.
- The deterministic simulator supports one to four probes, temperature patterns, insertion,
  removal, battery changes, stale samples and connection loss.
- A sanitised recorded fixture replays the physical payloads in hardware-independent tests.

The `pitboss-v202-check` command validates this production adapter on the Raspberry Pi and emits a
privacy-safe snapshot. It is a milestone check, not a long-running service.

## Development

Python 3.11 through 3.13 is the supported range. Install the editable development environment:

```console
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run the hardware-independent checks:

```console
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy src tests
.venv/bin/python -m pytest
```

There is no Docker-based installation or development path.

## Security

Never commit Bluetooth addresses, LAN addresses, tokens, broker credentials, local configuration
or unredacted physical evidence. The proof discovers by advertised name and redacts conventional
Bluetooth addresses from errors. Plain HTTP in later versions will be for trusted LAN use only.

## Licence

The original code in this repository is available under the MIT Licence. Research provenance and
dependency notices are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[docs/provenance.md](docs/provenance.md).
