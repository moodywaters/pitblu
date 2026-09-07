# Provenance

Review performed on 4 September 2026. No source code was copied or substantially adapted. The
implementation is a clean expression of protocol facts that were compared across independent
sources.

| Source | Reviewed commit | Licence at commit | Use |
| --- | --- | --- | --- |
| `jaydenk/igrill-remote-server` | `7dd1b198cdcd3ef793b9908d7c24348f27c88940` | MIT, copyright 2022 Bendik Wang Andreassen and 2026 Jayden Kerr | Corroborated Bleak lifecycle, V202 service UUID and challenge sequence. No code copied or adapted. |
| `bendikwa/esphome-igrill` | `b5edba3c87d16ff96d4aa2ee90a20a1921fb80ce` | MIT, copyright 2022 Bendik Wang Andreassen | Primary protocol research reference for UUIDs, model detection, challenge sequence, payload byte order and unplugged sentinel. No code copied or adapted. |
| `pilot1981/weber-igrill-integration-HA` | `e89a7d87a541449b3593cad78ac7d93162b17ab5` | MIT, copyright 2016 Tore Birkeland and 2018 Bendik Wang Andreassen | Historical corroboration of authentication, probe and battery reads. No code copied or adapted. |
| `1mckenna/esp32_iGrill` | `45c5f1d30e8b781f1c99640cf8088f95f5ed1719` | MIT, copyright 2021 Logan McKenna | Corroborated explicit V202 UUID and MQTT-related device behaviour. No code copied or adapted. |
| `sanjay900/igrill` | `b85cf0962b74d3a652a295c53d27b6b3cf9f39fe` | No root licence file found | Read-only corroboration of Bleak pairing/authentication behaviour. No code copied, adapted or incorporated because permission was unclear. |

## Dependencies

| Dependency | Version | Licence | Purpose |
| --- | --- | --- | --- |
| aiomqtt | 2.5.1 | BSD-3-Clause, copyright 2020 SBT Instruments | Async MQTT client facade. |
| Bleak | 3.0.2 | MIT | Async BLE discovery and GATT client. |
| FastAPI | 0.141.1 | MIT | REST API, OpenAPI generation and request validation. |
| PyYAML | 6.0.3 | MIT | Safe parsing of optional startup configuration. |
| Uvicorn | 0.52.4 | BSD-3-Clause | Native ASGI server. |
| Hatchling | 1.32.0 | MIT | Build backend only. |
| HTTPX2 | 2.12.0 | BSD-3-Clause | Development-only API contract client. |
| types-PyYAML | 6.0.12.20260815 | Apache-2.0 | Development-only static type information. |
| pytest | 9.1.1 | MIT | Development tests only. |
| pytest-cov | 7.1.0 | MIT | Development coverage checks only. |
| Ruff | 0.16.6 | MIT | Development formatting and linting only. |
| mypy | 2.3.1 | MIT | Development type checking only. |

aiomqtt installs Eclipse Paho MQTT Python 2.1.0 as its transport dependency. Paho declares
`EPL-2.0 OR BSD-3-Clause`; this project relies on the BSD-3-Clause option. No aiomqtt or Paho source
was copied or adapted.

Dependency licences were reviewed from their project metadata or licence distributions. Transitive
dependencies will be captured in a lock or installation manifest before a distributable release.

## Direct physical protocol evidence

On 4 September 2026, the target V202 supplied sanitised payloads `140080` for an inserted probe at a
simultaneous displayed 20°C, `30f880` for unplugged characteristics, `3c` for 60 per cent battery,
and `000a000002` for the characteristic previously described as a one-byte unit flag. These facts
were observed directly and were not copied from third-party source. The acceptance record contains
no Bluetooth address or personal network configuration.

Version 0.2.0 records those bytes in `tests/fixtures/v202/physical-proof.json` and replays them
through the clean-room protocol decoder. The production adapter, state machine, discovery
supervisor and simulator are original project code. No additional external source or dependency
was introduced for this milestone.

## Excluded source

Version 0.5.0 introduces no new third-party dependency or copied/adapted code. Recovery, lifecycle,
diagnostics and persistence changes use the existing dependency set and Python standard library.

The leftover-connection recovery helper invokes the existing BlueZ `bluetoothctl` executable
through bounded Python subprocess calls. No BlueZ code was copied or adapted. The behaviour
addresses direct Pi evidence: SIGKILL left a registered device connected and fresh discovery
could not restore application readings. BlueZ remains an operating-system prerequisite.

`elupus/togrill-bluetooth` was not researched or used because it targets ToGrill-branded hardware,
not the Weber iGrill protocol.

## v0.6.0 native deployment

The deployment scripts, offline SQLite backup/token operations and unit file are original project
code. No third-party source was copied or adapted and no Python dependency was added. They invoke
the existing operating-system systemd, BlueZ, shadow account tools and util-linux flock/runuser
utilities. These remain installed system prerequisites rather than bundled source.
