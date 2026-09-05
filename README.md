# pitboss-admin

`pitboss-admin` is a planned headless, API-first Raspberry Pi gateway for Weber iGrill
thermometers. Development is deliberately gated. Version 0.4.0 adds a shared telemetry event path,
MQTT publishing, SSE and stale-reading handling to the tested API and device foundation.

The resilience controller and native service deployment belong to later milestones and are not
implemented yet.

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

## v0.3.0 API and configuration

- FastAPI exposes versioned discovery, device, operation, telemetry and configuration resources.
- Slow device actions run as tracked background operations and return HTTP 202.
- SQLite persists administrative state, never temperature history.
- Configuration layers defaults, YAML, environment and transactional persisted overrides.
- ETags prevent lost configuration updates.
- Bearer tokens are stored only as salted scrypt hashes and can be rotated.
- Secret resources are write-only and validation errors never echo submitted values.

Run `pitboss-api` for the native development server. Its safe package default is loopback-only with
authentication disabled. Non-loopback binding is rejected unless token authentication is enabled.
See [REST API](docs/api.md) and [configuration](docs/configuration.md).

## v0.4.0 telemetry

- One canonical event model feeds bounded recent history, SSE and MQTT.
- MQTT uses the configurable `pitboss/v1` topic tree, JSON payloads and QoS 1.
- Service availability has a retained Last Will; state and availability are retained while raw
  temperatures are not.
- Connected devices are polled continuously using the configured probe interval.
- Probe and battery REST state explicitly reports freshness and becomes unavailable after the
  configured stale threshold.
- Physical and simulated events use the same schema and always identify their source.

MQTT remains disabled by default. See [MQTT](docs/mqtt.md) and [REST API](docs/api.md).

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
Bluetooth addresses from errors. Plain HTTP is for trusted LAN use only and must never be exposed
directly to the internet.

## Licence

The original code in this repository is available under the MIT Licence. Research provenance and
dependency notices are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[docs/provenance.md](docs/provenance.md).
