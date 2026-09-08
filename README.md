# pitboss-admin

A native Raspberry Pi gateway for the Weber iGrill V202. It reads probe temperatures
and battery state, offers REST administration, and shares live telemetry through
SSE and optional MQTT. There is no built-in web dashboard or cook-history database.

## Release status

**Current released version: v0.6.0.** The v0.9.0 release audit is in progress, not
released. Full physical acceptance and the minimum 16-hour soak remain v1.0.0 gates.
Two physical probes and battery readings have been demonstrated on the target Pi;
do not interpret this as completed overnight reliability or four-inserted-probe testing.

## Start here

- For cooks: [plain-English overview](docs/bbq-overview.md) and [quick start](docs/bbq-quick-start.md).
- For operators: [installation](docs/installation.md), [backup, upgrade and rollback](docs/upgrade-and-rollback.md), [troubleshooting](docs/troubleshooting.md).
- For frontend builders: [complete frontend and AI integration guide](docs/frontend-integration.md).
- For contributors: [development and checks](docs/development.md) and [contributing](CONTRIBUTING.md).
- For everything else: [documentation index](docs/README.md).

## Current functionality

- Explicit discovery and registration with stable public device identifiers.
- One active thermometer at a time, with up to four logical probe channels.
- Persistent desired connection state, supervised recovery and bounded diagnostics.
- Raw Celsius readings, probe presence, battery level and explicit freshness.
- Versioned REST, asynchronous operations, token authentication and rotation.
- Typed, version-checked configuration and write-only MQTT password management.
- Live SSE and MQTT JSON telemetry, QoS 1, retained availability and Last Will.
- Native installer, dedicated account, hardened systemd supervision, protected
  backups, upgrade, rollback and non-destructive uninstall.
- A simulator and hardware-independent tests on Python 3.11, 3.12 and 3.13.

See the [integration guide](docs/frontend-integration.md) for implemented behaviour
and limitations, including restart-required settings and no replayable temperature
history. MQTT is optional and disabled by default. There is no Docker deployment,
heating control, alarm or notification service.

## Security

The managed installer defaults to loopback with token authentication. Development
defaults differ; follow the installation guide for a managed service. Non-loopback
access requires a token. Plain HTTP is for trusted networks only: never expose the
gateway directly to the internet. Keep tokens, broker passwords, Bluetooth addresses,
private network configuration and database backups out of GitHub and support logs.

## Project records and licence

[CHANGELOG.md](CHANGELOG.md) records releases. [Physical acceptance](docs/physical-acceptance.md)
distinguishes completed checks from outstanding gates. Historical evidence is
labelled separately and is not an installation guide.

Original code is under the [MIT Licence](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md)
and [provenance](docs/provenance.md). The v0.9.0 licence audit is not yet complete.
