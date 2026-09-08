# pitblu

<p align="center">
  <img src="docs/assets/pitblu-logo.jpg" alt="pitblu logo: blue barbecue smoker with blue and green smoke" width="280">
</p>

An API-first Bluetooth gateway for Weber iGrill thermometers, built for Raspberry Pi.
Read probe temperatures and battery state, manage connections through REST, and
share live telemetry through MQTT and Server-Sent Events.

## Components

One repository for two independently deployable components:

- [pitblu-core](pitblu-core/README.md): the Raspberry Pi hardware gateway.
- [pitblu-web](pitblu-web/README.md): reserved for the future web frontend.

Shared documentation lives in `docs/`. Gateway source, tests, packaging and native
deployment tools live in `pitblu-core/`. There is no implemented web application yet.

## Release status

**Current candidate: v0.9.0rc1.** This is pre-release software, not a final v0.9.0
release. Clean-install validation and the full physical acceptance suite, including
a minimum 16-hour soak, remain release requirements. See the
[acceptance checklist](docs/physical-acceptance.md) for verified results and open gates.

## Requirements

- Raspberry Pi with Bluetooth and 64-bit Raspberry Pi OS Trixie.
- Python 3.11–3.13, BlueZ and systemd; the physical target uses Python 3.13.
- Weber iGrill V202 and compatible probes; one active thermometer at a time.
- Optional MQTT broker. No containers or built-in web dashboard are required.

Start with [native installation](docs/installation.md). For a fresh OS setup,
use the [rebuild checklist](docs/rebuild-checklist.md).

## Start here

- For cooks: [plain-English overview](docs/bbq-overview.md) and [quick start](docs/bbq-quick-start.md).
- For operators: [installation](docs/installation.md), [backup, upgrade and rollback](docs/upgrade-and-rollback.md), [troubleshooting](docs/troubleshooting.md).
- For frontend builders: [complete frontend and AI integration guide](docs/frontend-integration.md).
- For contributors: [development and checks](docs/development.md) and [contributing](CONTRIBUTING.md).
- For everything else: [documentation index](docs/README.md).

## Current gateway functionality

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
distinguishes completed checks from outstanding gates. Active documentation covers v0.9.0 onward; earlier records remain in Git history.

Original code is under the [MIT Licence](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md)
and [provenance](docs/provenance.md). The v0.9.0 licence audit is not yet complete.
