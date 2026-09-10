# Clean-Pi acceptance: v0.9.0

Status: **PASS**. Evidence recorded 10 September 2026 for the v0.9.0rc1
candidate at exact commit `f3bc11488e72b966676c0f3a1844ea218259ab90`.

This is the release record for the clean-install gate. Repeatable preparation and
installation instructions live in the [rebuild checklist](rebuild-checklist.md) and
[installation guide](installation.md). The full four-probe physical suite and
minimum 16-hour soak remain separate v1.0.0 gates.

## Platform and source

| Check | Result | Sanitised evidence |
| --- | --- | --- |
| Fresh target | PASS | Raspberry Pi 4; Raspberry Pi OS Lite 64-bit; Debian 13 Trixie; no existing pitblu-core account or managed application, configuration or state roots. |
| Platform | PASS | aarch64; Python 3.13.5; BlueZ 5.82; Bluetooth enabled and active; clock synchronised. |
| Source | PASS | Cloned exclusively from the private GitHub repository; exact checkout `f3bc11488e72b966676c0f3a1844ea218259ab90`; clean working tree before testing. |
| Development checks | PASS | Ruff lint and format, strict mypy over 50 source files, installer shell syntax and all 114 tests passed; coverage 93.79% against a 90% threshold. |

## Installation and security

| Check | Result | Sanitised evidence |
| --- | --- | --- |
| Native installer | PASS | Interactive install completed, generated token was saved privately, and the installer left the service disabled and inactive. |
| Account and permissions | PASS | Dedicated nologin account belongs to the Bluetooth group; installed code and configuration are root-owned; the service account could not modify them. |
| Service hardening | PASS | Installed systemd restrictions matched the documented model; explicit enable and start succeeded. |
| Authentication | PASS | Health remained public. Ready, OpenAPI, Swagger, ReDoc, status and configuration schema rejected unauthenticated access with 401; authenticated access passed. |
| Resource controls | PASS | Oversized input returned a safe 413 response and authentication throttling returned 429. |
| Secret handling | PASS | Neither the administrator token nor MQTT password was found in the journal. No secret, address, raw log, database or backup content is retained in this record. |

## Physical and messaging acceptance

| Check | Result | Sanitised evidence |
| --- | --- | --- |
| REST onboarding | PASS | The V202 was discovered, registered and connected entirely through REST with stable public device ID `igrill-v202-cd09`; `bluetoothctl` was not used. |
| Probe state | PASS | Probes 1 and 2 were present and fresh; probes 3 and 4 were absent with fresh null values. Both available probes read 18.0°C against an 18°C display, a 0.0°C delta. |
| Battery | PASS | Physical 50% reading was fresh; its timestamp stayed stable between polls and advanced after the configured 300-second interval. |
| SSE and controls | PASS | Live SSE remained open until intentionally closed. Explicit disconnect and reconnect produced the expected desired and observed states. |
| Recovery | PASS | Service restart and Pi reboot restored persisted desired state and fresh polling automatically. |
| MQTT security | PASS | A loopback-only test broker rejected anonymous access. Separate least-privilege publisher and subscriber identities passed their allowed operations; subscriber publishing was denied. |
| MQTT contract | PASS | Configuration used REST and the write-only secret API. QoS 1, retained state, non-retained temperatures, physical source, timestamps, session IDs and sequences passed. |
| API-only mode | PASS | Disabling MQTT through REST preserved physical BLE and API operation. Mosquitto was installed only as acceptance infrastructure, not as a gateway runtime dependency. |

Manual discovery results are intentionally temporary. During acceptance, the
15-second background scan could invalidate an earlier scan result; completing scan
and registration promptly in one flow succeeded. This is an operational usability
observation already covered by the integration contract, not a release defect.

## Recovery and maintenance

| Check | Result | Sanitised evidence |
| --- | --- | --- |
| Protected backup | PASS | Backup storage was created lazily as root-owned mode 0700 and its contents remained protected. |
| Upgrade | PASS | A same-version upgrade from the same source commit created a new versioned release; health, authentication, device state and fresh readings passed. |
| Rollback | PASS | Rollback from the exact pre-upgrade backup restored the original release selection while preserving credentials, identity, settings and readings. |
| Non-destructive uninstall | PASS | The service was stopped and disabled while account, releases, configuration, state and backups remained. Documented restoration restored health, authentication, registration and fresh polling. |

## Dependency evidence

The dependency inventory was generated on Linux/aarch64 with Python 3.13.5 using
the same script and pinned Hatchling version as CI. It was valid JSON of roughly
18 KB, and checks found no home or managed-state paths, authorisation values,
bearer tokens or password strings. The generated file is not committed: CI remains
the normal source of per-Python dependency inventory and audit artefacts.

All v0.9.0 clean-install items are PASS. No v1.0.0 four-probe or soak-test result is
inferred from this acceptance record.
