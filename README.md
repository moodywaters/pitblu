# pitboss-admin

`pitboss-admin` is a planned headless, API-first Raspberry Pi gateway for Weber iGrill
thermometers. Development is deliberately gated. Version 0.1.0 contains only the repository
scaffold and a focused physical BLE proof for the Weber iGrill V202.

The REST service, MQTT, persistence, simulator and native service deployment belong to later
milestones and are not implemented yet.

## v0.1.0 result

Version 0.1.0 passed its Raspberry Pi physical gate on 4 September 2026, demonstrating:

- discovery of the expected advertised name within 20 seconds;
- connection and Weber challenge/response initialisation;
- at least one inserted probe temperature, normalised to Celsius;
- the standard Bluetooth battery percentage;
- output containing no Bluetooth address.

See [physical acceptance](docs/physical-acceptance.md) for the sanitised evidence. Later milestones
remain unimplemented.

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
