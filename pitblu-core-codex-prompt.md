# AI continuation guide: pitblu-core

## Current state

Repository: https://github.com/moodywaters/pitblu (private).
One repository contains pitblu-core, the gateway, and pitblu-web, a future frontend
placeholder. Shared documentation is in docs/. Never make the repository public
without the owner's explicit instruction.

The current candidate is 0.9.0rc1, revision f7d3879. It is installed on the operator's
Raspberry Pi. It is not the final v0.9.0 release. Read docs/README.md,
docs/frontend-integration.md and docs/v0.9.0-plan.md before continuing.

## Architecture and boundaries

The Python gateway runs natively on Raspberry Pi OS, using FastAPI, Bleak, SQLite,
SSE and optional MQTT. No Docker. Keep Bluetooth behind the adapter interface.
Only explicitly registered devices may reconnect automatically. The implementation
owns one active thermometer at a time and supports four logical probe channels.

REST owns administration. MQTT is telemetry only. Public device identifiers are
separate from private hardware addresses. Never add cook sessions, history,
graphs, food semantics, alarms or a browser UI to the gateway. The future web
application owns those features and its own database.

The target specification is pitblu-core-project-plan.md. It describes release
requirements; the integration guide describes actual implemented behaviour.
Do not invent missing capabilities or treat an unrun acceptance test as passed.

## Working rules

- Inspect Git status and preserve unrelated user changes.
- Keep code, tests, documentation and provenance together in reviewable commits.
- Use British English. Do not use em dashes.
- Windows is the development host; the operator runs supplied commands over Pi SSH.
- Small related batches of Pi commands are permitted; wait for their output.
- Never print or request tokens, passwords, private addresses or raw databases.
- Native service changes are disruptive: schedule outside an active cook.
- No automatic updates, arbitrary command API or direct internet exposure.
- Do not delete protected recovery data as incidental cleanup.

## Validation recorded for the current candidate

114 hardware-independent tests pass on the Pi's Python 3.13.5, coverage 93.79%.
Linux CI passes Python 3.11, 3.12 and 3.13, including dependency scanning.
The Python wheel builds and contains the project licence.

On 8 September 2026 the operator verified migrated administrator authentication,
physical probe readings on channels 1 and 2, 50% battery, MQTT connection and
delivery on pitblu topics. Service availability was retained at QoS 1;
physical temperatures were non-retained at QoS 1. Reboot recovery restored
fresh readings with no service restarts. Bluetooth power and clock synchronisation
reported true. A simultaneous device-display comparison has not been confirmed
for this candidate. See docs/physical-acceptance.md.

## Deployment

Service/account: pitblu-core. Commands: pitblu-api, pitblu-state,
pitblu-ble-proof and pitblu-v202-check. Python package: pitblu_core.
Environment prefix: PITBLU_. Managed paths: /opt/pitblu-core,
/etc/pitblu-core and /var/lib/pitblu-core. Backups: /var/backups/pitblu-core.
MQTT publisher identity: pitblu-core; base topic: pitblu.
API uses loopback port 8080 and the operator's original administrator token.
Do not hard-code personal secrets or infer current PIDs.

The operator retains disabled predecessor files and protected rollback backups.
Cleanup is deferred and is not a prerequisite for progression.
No spare microSD card or second Pi is currently available for clean-Pi testing.

## Remaining gates

Finish the v0.9.0 documentation/security/provenance audit and clean-Pi acceptance.
The owner authorised merging PR 8 into main on 8 September 2026. This authorises
source integration, not a final release or waiver of physical acceptance. Never
relabel migration on an existing OS as a clean installation. Do not tag a final
release until its required evidence is recorded.

Before v1.0.0, run the complete physical acceptance suite and at least 16 hours
of monitored physical operation, recording freshness, MQTT receipt, gaps and
automatic recovery. An idle running process is not a soak-test pass.

## Development commands

Run from pitblu-core/ with its development virtual environment:
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m pytest
bash -n deploy/manage.sh

Read docs/development.md for setup and docs/frontend-integration.md for every
REST resource, setting, SSE event and MQTT payload. pitblu-web is not implemented.
