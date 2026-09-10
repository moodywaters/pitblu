# AI continuation guide: pitblu-core

## Current state

Repository: https://github.com/moodywaters/pitblu (private). One repository contains
pitblu-core, the gateway, and pitblu-web, a future frontend placeholder. Shared
documentation is in docs/. Never make the repository public without the owner's
explicit instruction.

The source version is 0.9.0 beta. Its runtime was clean-installed and physically
accepted while labelled 0.9.0rc1 at exact commit
`f3bc11488e72b966676c0f3a1844ea218259ab90`. Release preparation changes metadata
and documentation only, not runtime code. Consult `docs/release-status.md` and GitHub
before claiming that the `v0.9.0` tag or release has been published.

## Architecture and boundaries

The Python gateway runs natively on Raspberry Pi OS using FastAPI, Bleak, SQLite,
SSE and optional MQTT. No Docker. Keep Bluetooth behind the adapter interface. Only
explicitly registered devices may reconnect automatically. The implementation owns
one active thermometer at a time and supports four logical probe channels.

REST owns administration. MQTT is telemetry only. Public device identifiers are
separate from private hardware addresses. Never add cook sessions, history, graphs,
food semantics, alarms or a browser UI to the gateway. The future web application
owns those features and its own database.

The target specification is `pitblu-core-project-plan.md`. The integration guide
describes implemented behaviour. `CHANGELOG.md` is the canonical human-readable
version history; Git tags and releases are authoritative for published revisions.

## Working rules

- Inspect Git status and preserve unrelated user changes.
- Keep code, tests, documentation and provenance together in reviewable commits.
- Use British English. Do not use em dashes.
- Windows is the development host; the operator runs supplied commands over Pi SSH.
- Never print or request tokens, passwords, private addresses or raw databases.
- Native service changes are disruptive: schedule them outside an active cook.
- No automatic updates, arbitrary command API or direct internet exposure.
- Do not delete protected recovery data as incidental cleanup.
- Do not infer release, tag or acceptance results that were not actually observed.

## v0.9.0 acceptance evidence

On a fresh Raspberry Pi OS Lite 64-bit Trixie system, exact commit
`f3bc11488e72b966676c0f3a1844ea218259ab90` passed Ruff, formatting, strict typing,
installer shell syntax and all 114 tests with 93.79% coverage on Python 3.13.5.
BlueZ 5.82, Bluetooth and clock synchronisation were healthy.

Native install, dedicated-account permissions, systemd hardening, authentication,
request limits and journal secret checks passed. REST-only V202 onboarding, two
available probes at 0.0°C display delta, absent channels 3 and 4, 50% battery and
battery cadence passed. SSE, least-privilege MQTT, QoS/retention payload behaviour,
API-only mode, explicit controls, restart and reboot recovery, protected backup,
same-version upgrade/rollback and non-destructive uninstall/restoration passed.
See `docs/clean-pi-acceptance.md` for the sanitised record.

The Linux/aarch64 Python 3.13.5 dependency inventory was generated and sanitised on
the clean Pi but is not committed. CI remains the normal source of per-Python
inventory and dependency-audit artefacts.

## Deployment

Service/account: pitblu-core. Commands: pitblu-api, pitblu-state,
pitblu-ble-proof and pitblu-v202-check. Python package: pitblu_core. Environment
prefix: PITBLU_. Managed paths: `/opt/pitblu-core`, `/etc/pitblu-core` and
`/var/lib/pitblu-core`. Backups: `/var/backups/pitblu-core`. MQTT base topic:
pitblu. The API uses loopback port 8080 by default.

GitHub is the release source of truth. Clone with a least-privilege authenticated
identity, check out the reviewed tag or full commit, verify it, and install from the
pitblu-core component. Never place GitHub or application credentials in commands,
logs or source. Mosquitto and its clients are optional acceptance infrastructure,
not gateway runtime prerequisites.

## Remaining work

Before publishing v0.9.0, the release pull request must pass supported-Python CI and
final review, then receive explicit owner approval to merge. Do not tag or create a
GitHub release without that approval. After the merged release and tag exist, run
the requested final Pi deployment and focused smoke validation from that exact tag.

For v1.0.0, run the complete four-inserted-probe physical acceptance suite and at
least 16 hours of monitored physical operation, recording freshness, MQTT receipt,
gaps and automatic recovery. An idle running process is not a soak-test pass. These
gates are not part of v0.9.0 and remain pending.

## Development commands

Run from pitblu-core with its development virtual environment:

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest
bash -n deploy/manage.sh
```

Read `docs/development.md` for setup and `docs/frontend-integration.md` for every
REST resource, setting, SSE event and MQTT payload. pitblu-web is not implemented.
