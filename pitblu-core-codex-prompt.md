# Master Codex Prompt: Build `pitblu-core`

## Current documentation entry point

Repository layout update: `moodywaters/pitblu` is the single private repository.
`pitblu-core/` contains the Python project, tests and deployment tools; `pitblu-web/`
is a documentation-only placeholder for a future separately deployable frontend.
Shared documentation and this handoff remain at repository root. Run Python checks
and installer commands from the gateway component directory. Do not implement a
frontend as part of the gateway audit. Historical instructions below do not override
this layout or the current milestone gates.

Naming update, 8 September 2026: the user requires the application/repository to
be named `pitblu-core` everywhere in the current project. Python uses `pitblu_core`,
commands `pitblu-`, environment variables `PITBLU_` and default MQTT base `pitblu`.
Historical summaries below have been normalised to this naming convention and
must not be treated as literal records of installed paths, hostnames or credentials.
The running Pi has NOT been migrated. Inspect its actual deployment before preparing
the controlled cutover in `docs/rename-migration.md`. Preserve its state and secrets.
Do not rewrite Git history or remove recovery backups as an incidental rename step.

8 September 2026 candidate work: v0.9.0rc1 adds request/body/SSE limits, protected
schema/docs routes, safe startup failures, bounded token-hash jobs, physical battery
cadence/timestamps, host Bluetooth/clock diagnostics and managed-file symlink guards.
Documentation and tests accompany these changes. See `docs/unreleased.md`,
`docs/security-review.md`, `docs/dependency-audit.md` and `docs/clean-pi-acceptance.md`.
The installed Pi remains v0.6.0. Clean-Pi acceptance requires a spare card/target;
do not overwrite the working installation or mark v0.9.0 complete without evidence.

Released baseline: v0.6.0; v0.9.0 audit in progress; v1.0.0 physical suite and
minimum 16-hour soak pending. Use [the documentation index](docs/README.md) for
current guides and [the active audit plan](docs/v0.9.0-plan.md) for current work.
The original instructions and dated continuation records below are retained as
development history, not current installation commands. Old milestone plan files
have been removed; consult Git history only when historical context is needed.
The user's later instruction permits small related batches of Pi commands.

Development update, 8 September 2026: partial device PATCH now distinguishes an
omitted friendlyName from explicit null, and configured CORS exposes ETag and
X-Correlation-ID while allowing the correlation request header. Regression tests
reproduced both old failures and pass with the fixes. These changes are unreleased
and not installed on the Pi. See `docs/unreleased.md`; current user guides retain
the released v0.6.0 baseline until a validated upgrade. Continue the remaining
audit, including authentication/resource limits, licence review and clean-Pi tests.

Documentation cleanup, 8 September 2026: the six completed milestone plans are
removed from the working tree. Any reference to them in the dated records below
is historical and must not be followed as a current task. Dated acceptance evidence
is now `docs/history/acceptance-evidence.md`; `docs/physical-acceptance.md` is the
current checklist. Current runbooks describe released v0.6.0, not an unreleased
v0.9.0 runtime. Preserve licence/provenance and release records while removing
superseded operating instructions. No Pi changes are part of this cleanup.

You are implementing a new open-source-ready project called `pitblu-core`. Work as a careful senior engineer. Build incrementally, verify every milestone, and keep documentation, tests and provenance current in the same changes as the code.

## Mission

Create a headless, API-first service running natively on a Raspberry Pi. It discovers, registers, connects to and monitors a Weber iGrill V202/iGrill 2 over Bluetooth Low Energy. All administrative and operational control is exposed through a versioned REST API. Raw reusable telemetry is published through MQTT. Live API events are also exposed through Server-Sent Events.

This is the hardware gateway only. A separate future web application will provide cook sessions, history, graphs, alarms and other user-facing features.

## Working approach

1. Inspect the current repository and connected GitHub state before changing anything.
2. Use the private `moodywaters/pitblu` repository. Do not create a separate gateway repository or make it public.
3. Create a written implementation plan mapped to the milestones below.
4. Begin with `v0.1.0`. Do not attempt to build every milestone in one pass.
5. Complete code, tests, documentation and provenance for a milestone before advancing.
6. Stop at any physical hardware validation point and ask me to run the required Raspberry Pi command.
7. Give me exactly one Raspberry Pi command at a time. Wait for its output before giving the next command.
8. Never request or display my MQTT password, API token or other secrets. Never put secrets, private Bluetooth addresses, LAN addresses or personal configuration in GitHub.
9. Use British English in documentation. Do not use em dashes.
10. Make small, reviewable commits aligned with milestones. Run relevant checks before committing or pushing. Do not merge failing work.

## Confirmed target environment

- Raspberry Pi 4 Model B Rev 1.4
- Raspberry Pi OS build dated 18 June 2026
- Debian GNU/Linux 13.5 Trixie base
- 64-bit ARM (`aarch64`)
- Python 3.13.5 installed
- BlueZ 5.82 installed
- Onboard adapter `hci0`, powered, active and unblocked
- Hostname `pitblu`
- Ethernet currently preferred, with Wi-Fi available
- Native Python deployment managed by `systemd`
- Docker is explicitly prohibited, including Dockerfiles and Compose files

The physical thermometer advertises as `iGrill_V202-CD09`. Its private Bluetooth address must be discovered or supplied through protected local configuration and must never be committed.

Manual validation already proved that the Pi can discover the device and establish a basic BlueZ connection. The device exposes Generic Access, Generic Attribute, Device Information, Battery Service and Weber vendor-specific services. A basic `bluetoothctl` connection closes when scanning stops, so the implementation must correctly perform the Weber-specific initialisation/authentication sequence.

## Required technology and architecture

- Python compatible with 3.11 through 3.13, tested on 3.13
- `asyncio`
- FastAPI and generated OpenAPI
- Bleak for BLE access, behind an internal device-adapter interface
- A maintained Python MQTT client with asyncio-safe integration
- SQLite for administrative state only
- Pydantic models and typed configuration
- Structured logging suitable for `journald`
- Native virtual environment and `systemd`
- No containerisation

Do not use `elupus/togrill-bluetooth`; it targets ToGrill-branded hardware and is not a Weber iGrill library.

## Architectural boundary

`pitblu-core` owns:

- BLE discovery and communication
- Explicit device registration
- Connection lifecycle, timeouts and recovery
- Probe and battery acquisition
- REST control and current state
- SSE live events
- MQTT publishing
- Configuration, authentication, health and diagnostics
- Administrative persistence and bounded operational events
- Simulation and hardware-independent testing

It must not contain:

- Cook sessions or temperature history
- Cook database
- Graphs or browser dashboard
- Food names or probe roles
- Timers or target-temperature alarms
- User notifications
- Estimated completion times
- MQTT administrative commands
- Internet-facing deployment features

## Device onboarding contract

- Connect automatically only to explicitly registered devices.
- A client starts discovery and receives supported discovered devices.
- `POST /api/v1/devices` accepts a discovered Bluetooth address, optional friendly name, initial connect choice and automatic-reconnection choice.
- Registration assigns a stable public identifier, for example `igrill-v202-cd09`.
- Normal REST URLs, responses and MQTT topics use the stable identifier, never the Bluetooth address.
- An add-and-connect request may register the device and begin an asynchronous connection operation.
- Persist registered devices and desired connection state across restarts.
- Nearby unregistered Weber devices may appear temporarily in discovery results but must never be connected automatically.

## Connection state model

Implement an explicit, testable per-device state machine with at least:

- `discovered`
- `connecting`
- `initialising`
- `connected`
- `polling`
- `degraded`
- `backoff`
- `disconnected`
- `unsupported`

Represent desired state separately from observed state. `connect` sets desired state to connected. Unexpected loss enters recovery while desired state remains connected. `disconnect` sets desired state to disconnected and cancels retries. A forced reconnect bypasses current backoff.

## REST contract

Use `/api/v1` for versioned resources.

### Service

- `GET /health`, minimal unauthenticated liveness only
- `GET /ready`, authenticated readiness
- `GET /api/v1/status`, authenticated operational summary

### Bluetooth and discovery

- `GET /api/v1/bluetooth`
- `POST /api/v1/scans`
- `GET /api/v1/scans/{scanId}`

### Devices

- `GET /api/v1/devices`
- `POST /api/v1/devices`
- `GET /api/v1/devices/{deviceId}`
- `PATCH /api/v1/devices/{deviceId}`
- `DELETE /api/v1/devices/{deviceId}`
- `POST /api/v1/devices/{deviceId}/connect`
- `POST /api/v1/devices/{deviceId}/disconnect`
- `POST /api/v1/devices/{deviceId}/reconnect`
- `GET /api/v1/devices/{deviceId}/probes`
- `GET /api/v1/devices/{deviceId}/battery`

### Operations and events

- `GET /api/v1/operations`
- `GET /api/v1/operations/{operationId}`
- `GET /api/v1/events`
- `GET /api/v1/events/stream`, using SSE

### Configuration and secrets

- `GET /api/v1/config`
- `PATCH /api/v1/config`
- `GET /api/v1/config/schema`
- `POST /api/v1/config/validate`
- `PUT /api/v1/config/secrets/{secretName}`
- `DELETE /api/v1/config/secrets/{secretName}`

Slow actions return `202 Accepted` plus an operation resource. Creation returns `201 Created`. Use `422` for validation errors, `409` for state conflicts and `401`/`403` for authentication/authorisation. Use one consistent safe JSON error envelope containing a stable error code, human-readable message, correlation identifier and optional details. Make reads and repeated connect/disconnect requests idempotent. Serialise conflicting operations per device.

## Configuration contract

Every application-level setting must be represented through REST so a future frontend can configure normal operation without SSH or direct file editing.

For each setting expose:

- Effective value
- Source: default, YAML, environment or persisted override
- Type and description
- Default, minimum, maximum and allowed values
- Editability
- Sensitivity
- Whether restart is required

Use configuration versions or ETags for optimistic concurrency. Validate a proposed update as a whole and persist it transactionally. Never partially apply an invalid update. Record successful changes as safe operational events.

Secrets are write-only. Responses expose only whether a secret is configured and when it changed. Never reveal secret values in responses, logs, events or diagnostics. Deployment-level settings such as filesystem paths and the Linux service account may be startup-only or read-only.

MQTT must be configurable for a local, remote or hosted broker, optional TLS, authentication, base topic, port, QoS and disabled API-only operation.

## API authentication and exposure

- Default API port: 8080, configurable
- Trusted-LAN installation binds to `0.0.0.0`
- Loopback-only mode binds to `127.0.0.1`
- Bearer-token authentication required for any non-loopback binding
- `/health` is unauthenticated and reveals only minimal liveness
- `/ready` and all `/api/v1/*` endpoints require authentication in trusted-LAN mode
- Installation generates a cryptographically secure administrator token and displays it once
- Persist only a secure token hash
- Provide authenticated token rotation and return the replacement token once
- Permit disabled authentication only with loopback binding
- Reject unauthenticated non-loopback configuration
- Do not implement built-in HTTPS in version one
- Document plain HTTP as trusted-LAN only and never suitable for direct internet exposure

## MQTT contract

Default base topic is `pitblu`, configurable. MQTT schema version `v1` is independent of the REST API version.

Publish:

- `pitblu/v1/service/availability`
- `pitblu/v1/devices/{deviceId}/availability`
- `pitblu/v1/devices/{deviceId}/connection`
- `pitblu/v1/devices/{deviceId}/battery`
- `pitblu/v1/devices/{deviceId}/probes/{probeNumber}/availability`
- `pitblu/v1/devices/{deviceId}/probes/{probeNumber}/temperature`

All payloads are JSON. A temperature payload contains:

```json
{
  "schemaVersion": 1,
  "deviceId": "igrill-v202-cd09",
  "probe": 1,
  "temperatureC": 112.4,
  "observedAt": "2026-09-04T10:15:32.481Z",
  "sequence": 1842,
  "source": "physical"
}
```

Use one-based probe numbers. Use UTC ISO 8601 timestamps. All version-one publications use QoS 1, so consumers must tolerate duplicates and can use sequence numbers for deduplication.

Retain service availability, device availability, connection state, battery and probe availability. Do not retain temperatures. Implement a retained MQTT Last Will for service availability. Do not accept commands over MQTT. Simulation uses identical topics with `source` set to `simulated`.

## Timing defaults

All are configurable through the configuration API:

- BLE scan duration: 5 seconds
- Missing-device scan interval: 15 seconds
- Connected background scan interval: 60 seconds
- Connection timeout: 10 seconds
- GATT initialisation timeout: 15 seconds
- Individual read timeout: 5 seconds
- Probe polling: 5 seconds
- Battery polling: 300 seconds
- Reading stale threshold: 15 seconds
- Degraded after 3 consecutive failed polling cycles
- Forced reconnect after 30 seconds without a valid reading
- Availability heartbeat: 60 seconds
- Reset backoff after 60 seconds of stable connection
- Reconnect delays: 2, 4, 8, 15, 30, then 60 seconds maximum
- Backoff jitter: plus or minus 20 per cent

Continuous discovery means an always-running discovery supervisor, not uninterrupted radio scanning. Avoid scanning behaviour that destabilises an active BLE connection.

## Data integrity

- Publish raw decoded Celsius values without smoothing.
- Reject documented invalid and sentinel values.
- Track observation time, sequence and fresh/stale status.
- Separate service, device and probe availability.
- Use UTC internally and report clock synchronisation health.
- Do not interpret temperatures as food, pit or cook semantics.
- Do not immediately declare the device disconnected after one probe read failure.

## Simulation

Implement a disabled-by-default simulated adapter using the same internal interface and event path as physical hardware. Support one to four probes, rising/falling/stable patterns, probe insertion/removal, battery changes, connection loss, stale readings and recovery. Simulated output must always say `source: simulated`.

## Persistence and filesystem

SQLite stores administrative state only: registered devices, friendly names, desired states, persisted runtime settings, operation metadata and bounded operational events. Do not store cook history or long-term temperature history.

Target native layout:

- `/opt/pitblu-core/`, application and virtual environment
- `/etc/pitblu-core/config.yaml`, non-secret startup configuration
- `/etc/pitblu-core/environment`, protected environment secrets where required
- `/var/lib/pitblu-core/`, SQLite state

Use a dedicated low-privilege service account. Provide secure permissions, a hardened but functional `systemd` unit, graceful termination, `journald` logging, and documented install, upgrade, backup, rollback and uninstall procedures.

## Existing Mosquitto environment

Mosquitto is already installed locally on the target Pi and listening on port 1883. Anonymous access is disabled. Password authentication is enabled. The `pitblu-core` MQTT identity is restricted by ACL to `pitblu/#`. Local authenticated publish/subscribe and retained messaging have been verified.

Treat local Mosquitto as the deployment default, not a hard-coded dependency. Do not overwrite or expose the existing password. Provide configuration examples and optional broker setup documentation. Additional consumers such as Node-RED should use separate least-privilege credentials.

## Testing

Include:

- Unit tests for payload and temperature decoding
- Recorded, sanitised BLE payload fixtures
- State-machine tests
- Timeout and backoff tests using controlled time, not real sleeps
- MQTT publisher and failure tests using fakes or test doubles
- API contract, authentication, idempotency and concurrency tests
- Configuration validation, persistence and optimistic-concurrency tests
- Secret-redaction tests
- SSE tests
- Graceful shutdown tests
- Simulator tests
- Formatting, linting, type checking and test workflows in GitHub Actions

Hardware-dependent tests must be separate and must not make ordinary CI fail when no Bluetooth adapter or iGrill is present.

## Documentation and public-source readiness

Create and maintain:

- `README.md`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `docs/architecture.md`
- `docs/api.md`
- `docs/configuration.md`
- `docs/bluetooth.md`
- `docs/mqtt.md`
- `docs/installation.md`
- `docs/upgrade-and-rollback.md`
- `docs/troubleshooting.md`
- `docs/development.md`
- `docs/physical-acceptance.md`
- `docs/provenance.md`
- Architecture Decision Records for significant choices

Use an MIT licence only after confirming compatibility with all incorporated code and dependencies.

Before copying or substantially adapting third-party code, inspect its exact licence and relevant file history. In the same change, record repository URL, exact commit, licence, copyright, affected component, whether code was copied or adapted, and the nature of modifications. Distinguish dependencies, copied code, adapted code, protocol research and general architectural influence.

Research these projects as references:

- `jaydenk/igrill-remote-server`
- `bendikwa/esphome-igrill`
- `pilot1981/weber-igrill-integration-HA`
- `1mckenna/esp32_iGrill`
- `sanjay900/igrill`

Prefer clean implementation from documented protocol understanding when practical. Do not copy code with an absent, unclear or incompatible licence. Do not claim inspiration, reuse or compatibility without evidence.

## Milestones

### `v0.1.0`: physical BLE proof

- Repository scaffold
- Dependency and licence review
- CI and documentation structure
- Focused Bleak-based BLE spike
- Discover the physical V202
- Perform required initialisation/authentication
- Read at least one physical probe and battery percentage
- Document findings and sanitised protocol evidence

Do not proceed until the physical read succeeds or the blocker is accurately diagnosed and agreed with me.

### `v0.2.0`: device foundation

- Production iGrill adapter
- Continuous discovery supervisor
- Four probes and probe presence
- Explicit connection state machine
- Simulator
- Sanitised recorded BLE fixtures

### `v0.3.0`: API and configuration

- REST contract
- Asynchronous operations
- Authentication and token rotation
- Complete typed configuration API
- Administrative persistence

### `v0.4.0`: telemetry

- MQTT contract and Last Will
- SSE event stream
- Stale-data handling
- Canonical internal event schema

### `v0.5.0`: resilience

- Reconnection and backoff
- Concurrency controls
- Diagnostics and bounded events
- Graceful shutdown

### `v0.6.0`: native deployment

- Installer
- Dedicated account and permissions
- `systemd`
- Upgrade, backup, rollback and uninstall

### `v0.9.0`: release candidate

- Clean-Pi installation test
- Security review
- Documentation audit
- Third-party provenance and licence audit

### `v1.0.0`: physical release

- Complete physical acceptance suite
- Successful at-least-16-hour soak test

## Mandatory `v1.0.0` release gates

- Discover the V202 within 20 seconds.
- Register and connect entirely through REST.
- Resolve correct Weber GATT services.
- Detect all four inserted probe channels.
- Match iGrill display temperatures within 1 degree Celsius.
- Detect removal within 15 seconds.
- Read battery percentage.
- Reject invalid/sentinel temperatures.
- Mark stale data and publish unavailability correctly.
- Recover after iGrill power cycling, Bluetooth failure, Mosquitto restart and Pi reboot without manual service restart.
- Complete an at-least-16-hour physical soak without manual intervention; record and recover transient disconnects.
- Verify REST, async operations, SSE, MQTT schema, Last Will, configuration persistence, authentication and secret redaction.
- Verify clean native installation, automatic `systemd` startup, graceful shutdown, upgrade and rollback.
- Pass CI and complete documentation, provenance and licence audits.

## Start now

Begin only with repository inspection and the `v0.1.0` implementation plan. Report:

1. What currently exists.
2. The exact third-party licences and commits you intend to reference for the BLE spike.
3. The proposed minimal repository scaffold.
4. The smallest sequence that will prove physical V202 probe and battery reads.
5. Any decision you genuinely need from me.

Then implement `v0.1.0` incrementally. Do not start later milestones until the physical BLE proof and milestone checks are complete.

## Continuation handoff: 5 September 2026, after v0.4.0

This section is an additive progress record for an AI continuing the existing project. Preserve
the original specification above and the authoritative `pitblu-core-project-plan.md`. The
original "Start now" section describes the initial project state, not the current starting point.
Do not restart v0.1.0: v0.1.0 through v0.4.0 have been released. The next implementation milestone
is v0.5.0, subject to the user's direction to resume implementation. This handoff update itself
does not implement or complete any part of v0.5.0.

### Repository and released baseline

- Private repository: https://github.com/moodywaters/pitblu. Keep it private.
- Main branch: `main`.
- Latest release: https://github.com/moodywaters/pitblu/releases/tag/v0.4.0.
- v0.4.0 was merged through pull request #5; its release commit is `9bd8999` and its
  implementation commit is `6f0f014`. Resolve full commits from Git rather than guessing them.
- Earlier releases are tagged `v0.1.0`, `v0.2.0` and `v0.3.0`.
- At handoff, application package version is `0.4.0`. Inspect current Git state before proceeding;
  later commits may supersede this dated record.
- `docs/physical-acceptance.md` records sanitised evidence. `CHANGELOG.md`, `docs/mqtt.md`,
  `docs/api.md`, `docs/configuration.md` and `docs/provenance.md` describe the implemented state.
- `docs/v0.4.0-plan.md` still has a release-pending status/check box from before publication;
  the release and tag above establish that publication subsequently completed.

### Completed milestones and evidence

**v0.1.0: physical BLE proof, completed 4 September 2026.** Discovery, BlueZ pairing, Weber
initialisation and physical probe plus battery reads succeeded on the target Pi. Two attached
probes both decoded to 20 degrees Celsius and matched the physical display. Battery was 60 per
cent. Two other channels were absent. Private Bluetooth addresses were excluded from evidence.

Physical protocol findings to preserve:

- Inserted probe bytes `140080` encode 20 degrees Celsius. The V202 framing is three bytes;
  decode the leading 16-bit value using the existing protocol implementation.
- Unplugged bytes `30f880` are a sentinel, not a temperature.
- Battery bytes `3c` represent 60 per cent.
- Unit metadata `000a000002` is not a one-byte Fahrenheit flag. Its extended meaning remains
  undetermined. Do not reintroduce a Fahrenheit conversion: the raw Celsius interpretation was
  verified against the display.
- Authentication evidence is `zero-challenge-loopback-succeeded`.
- Early pairing and GATT timeouts were resolved during the spike. Preserve the explicit deadlines
  and Linux connection/service-resolution handling already implemented.
- Replay fixture: `tests/fixtures/v202/physical-proof.json`.

**v0.2.0: device foundation, completed 4 September 2026.** Production adapter, shared adapter
interface, discovery supervisor, connection-state/backoff models, four channels, simulator and
recorded fixture were implemented. The production adapter returned physical probes at 19 and
21 degrees Celsius, both confirmed on the display, two absent channels and 60 per cent battery.
Pi validation passed 47 tests at 94.03 per cent coverage with lint, formatting and typing clean.
The discovery and state-machine components are foundations; their existence does not imply the
full application recovery controller is integrated.

**v0.3.0: REST and configuration, completed 4 September 2026.** FastAPI resources, asynchronous
operation metadata, SQLite administrative persistence, layered configuration, ETags, token hashing
and rotation, and write-only secrets were implemented. Simulator health, scan, registration,
connection, four probes and battery were verified through REST on the Pi. The gate passed 58
tests at 93.28 per cent coverage with lint, formatting and typing clean.

An intentional documented API difference from the original onboarding wording is that registration
accepts an opaque `discoveryId` from a scan result, not a raw Bluetooth address. Preserve the
implemented public contract and privacy boundary. Refer to `docs/api.md` and the ADRs.

**v0.4.0: telemetry, released 5 September 2026.** Canonical events, bounded in-memory event fan-out,
SSE, MQTT QoS 1 topic mapping, retained service Last Will, continuous sampling and stale state
were implemented. Physical and simulated adapters share the event path. Live v0.4.0 transport
acceptance used the simulator, not another physical BLE acceptance run.

The final Pi candidate passed 71 tests at 93.26 per cent coverage on Python 3.13.5. Ruff checked
61 formatted files; strict mypy checked 37 source files. GitHub CI passed on Python 3.11, 3.12
and 3.13 before merge. A dependency deprecation warning in Starlette/AnyIO did not fail the gate.

Live Pi telemetry acceptance demonstrated:

- SSE carrying correct device identifiers, UTC sample times, four readings and increasing sequences.
- Fresh simulator recovery after reconnect, with sequence 23 advancing to 27 over 20 seconds.
- REST probe and battery values becoming unavailable, stale and numerically null after disconnect.
- Authenticated Mosquitto service availability retained at QoS 1 with `source: simulated`.
- Four MQTT temperatures at 20, 21, 22 and 23 degrees Celsius with the required envelope.
- A new subscription after disconnect receiving four retained stale probe-availability messages
  and zero temperature messages, confirming temperatures were not retained.
- Force-stopping the isolated test API causing Mosquitto to publish retained service unavailability
  at QoS 1, proving the broker Last Will.

Live testing caught and fixed two regressions. `TelemetryEvent` now accepts internal snake_case
field names as well as public aliases and rejects unknown fields, preserving `deviceId` and
`observedAt`. The live simulator uses an injected current clock for each new observation; the
deterministic test simulator may still use a fixed starting time. Do not anchor live sample times
to API startup or assume a fixed five-second advance matches elapsed time.

### Current implementation map

- `adapters/base.py`, `adapters/igrill_v202.py`, `adapters/simulated.py`: shared device boundary.
- `protocol.py`, `ble_spike.py`, `physical_check.py`: decoder and manual hardware checks.
- `discovery.py`, `connection.py`: discovery supervision and state/backoff foundations.
- `api.py`, `service.py`: HTTP transport and administrative operations with connected-device polling.
- `storage.py`, `configuration.py`, `auth.py`: administrative persistence, settings and tokens.
- `events.py`: canonical Pydantic events, recent history, bounded subscriber queues and SSE framing.
- `telemetry.py`: current snapshots, stale deadlines, REST freshness and per-topic event sequences.
- `mqtt.py`: aiomqtt publisher, topic mapping, retention and Last Will.

Paths in this map are relative to `pitblu-core/src/pitblu_core/`. Read implementation and tests before
changing behaviour. Runtime dependencies include aiomqtt 2.5.1, Bleak 3.0.2, FastAPI 0.141.1,
PyYAML 6.0.3 and Uvicorn 0.52.4. aiomqtt uses Paho MQTT 2.1.0 in the validated installation.
Consult `pyproject.toml` and provenance/notices for the current versions and licence record.

### Known limitations and v0.5.0 work

Do not mistake released milestone scope for v1.0.0 readiness. The following require attention
in the resilience milestone or subsequent planned work:

- A failed MQTT background task does not currently change HTTP liveness/readiness or expose a
  useful publisher status. During validation, a rejected stored credential left HTTP healthy while
  no MQTT message was published. Add safe task supervision and diagnostics, without logging secrets.
- Automatic MQTT reconnect and complete BLE recovery/backoff orchestration are not implemented.
  The sampling loop currently stops on a read exception. Persistent desired state is stored, but
  full restart recovery and connection-handle restoration must be implemented and verified.
- Serialisation of conflicting device operations, cancellation and bounded graceful shutdown need
  completion. The service currently owns one selected adapter; inspect multi-device implications.
- Current events/history are bounded but in memory. Complete the planned operational diagnostics
  and persistence without introducing temperature history.
- Last Will `observedAt` is the payload preparation time before broker connection, not the time
  of failure. MQTT cannot dynamically rewrite the pre-registered Will on disconnect. Consumers
  need receipt time for failure detection. Normal shutdown currently reuses that prepared payload.
- Event sequences are per topic and process, and reset on restart. Consider restart/session
  identification before claiming cross-restart deduplication guarantees.
- Stale REST clears battery and probe numeric values; MQTT stale transitions currently publish
  device/probe unavailability. Audit retained battery state, device deletion, disconnect semantics
  and repeated old snapshots when completing data-integrity/recovery behaviour.
- Battery is currently obtained in each full snapshot; the separate configured battery cadence
  and availability heartbeat need integration/audit. SSE idle comments are not MQTT heartbeats.
- Configuration metadata currently marks all settings restart-required. Some handlers read the
  current config while long-lived components capture startup settings; audit the effective runtime
  semantics rather than assuming every update is consistently hot-applied or deferred.
- Native installer, dedicated account, protected production filesystem layout, systemd, upgrade
  and rollback remain v0.6.0. Clean-Pi/security/provenance audits remain v0.9.0. Full physical
  acceptance and the 12-hour soak remain v1.0.0. None has been claimed complete.

### Working environment and current Pi state

Development has been performed on Windows in `C:\pitblu`; the application target is the Raspberry
Pi. The user runs Pi commands through SSH. Do not run Linux installation commands on Windows or
assume the agent has a direct Pi execution tool. The Pi development checkout is
`/home/john/pitblu-core` with virtual environment `/home/john/pitblu-core/.venv`.
This is a development layout, not the future `/opt` production installation.

The user explicitly updated their command preference: several related Pi commands may now be
provided in one block. This supersedes the earlier one-command-at-a-time rule. Wait for output
when the next step depends on it. Label Windows PowerShell versus Pi shell commands clearly.

The v0.4.0 test API ran on loopback port 8081 with simulation and an isolated database. It was
stopped by the Last Will test and has not been restarted in this handoff. Temporary test databases,
logs and retained MQTT test messages may remain on the Pi. A test database contains the broker
password and must remain protected deployment data; never package, print or commit it. Inspect
current state before cleanup and preserve the existing broker and its authentication/ACLs.

Do not assume old shell variables or process IDs survive a new SSH session. Identify the actual
process before stopping it. Do not export ad hoc helper variables prefixed `PITBLU_`: the config
loader treats that prefix as application configuration and rejects unknown settings.

Source archives were copied from Windows and extracted into the existing Pi checkout. One early
v0.4.0 archive had a `pitblu/` top-level directory and was initially extracted to the wrong sibling
directory; the correct installation used `--strip-components=1 -C /home/john/pitblu-core`.
Inspect archive contents before giving extraction instructions. Exclude Git metadata, virtual
environments, bytecode, caches, databases, logs, secrets and local config from every package.

During MQTT validation, typed credentials worked while a previously stored value did not. The
successful procedure verified broker authentication first, saved through the write-only API, then
compared the stored value locally without displaying either value. Restart was needed for the
publisher to load the changed credential. Never ask the user to paste a password into the chat.

### Resume procedure for a new AI

1. Read this appended handoff, the original specification and project plan, then inspect the
   current repository, tags, open PRs and local changes. Preserve any subsequent user work.
2. Treat v0.1.0 through v0.4.0 as released with the evidence and limitations above. Do not repeat
   completed hardware gates unless a change or new failure justifies regression validation.
3. When asked to continue implementation, write a v0.5.0 plan for supervised BLE/MQTT recovery,
   persistence integration, operation concurrency, safe diagnostics and graceful shutdown.
4. Use controlled time and test doubles for failure/recovery tests, then request targeted Pi
   validation. Never infer broker health from HTTP health alone.
5. Run Ruff lint, Ruff format check, strict mypy and pytest with the existing 90 per cent coverage
   gate. Keep hardware-independent CI working on Python 3.11 through 3.13.
6. Update documentation and provenance alongside code; use reviewed milestone commits and green
   CI before merging or releasing. Keep the repository private and do not advance to v0.6.0
   until v0.5.0 is verified.

## Continuation update: v0.5.0 candidate, 5 September 2026

The user authorised v0.5.0 implementation after the handoff above. Work is on
`codex/v0.5.0-resilience`; this is a candidate, not a released or Pi-accepted milestone.
Read `docs/v0.5.0-plan.md` for the required remaining target checks. Local validation passed 84
tests at 93.99 per cent coverage, Ruff and strict mypy. No new dependency was introduced.

The candidate adds MQTT retry/diagnostics/retained replay, BLE recovery and registered identity
restoration, control conflict handling, adapter ownership, bounded persistent operational events,
session IDs, stale battery invalidation and graceful shutdown. `/api/v1/diagnostics` and
`/api/v1/events/operations` are new protected resources. `/ready` returns 503 when enabled MQTT is
not connected. The SQLite identity column is additive. Legacy registrations require an explicit
fresh `discoveryId` selection using device PATCH before automatic restore; names are not identities.

Next: deliver the candidate source archive, run the Pi quality gate, then verify broker recovery,
application restart, persisted disconnect, physical V202 power-cycle recovery and shutdown. The
Pi's previous temporary API was stopped after the v0.4.0 Last Will test. Inspect processes before
changing runtime state. Do not mark v0.5.0 complete or start v0.6.0 until target acceptance passes.

### v0.5.0 Pi validation update, 5 September 2026

The first candidate passed all 84 Pi tests, lint, formatting and strict typing. Simulator
automatic restoration after application restart and persisted explicit disconnect both passed.
MQTT broker outage returned safe backoff diagnostics and readiness 503; recovery returned 200
without changing the application session. Retained online and offline availability passed QoS 1.
Idle outage detection uses the 60-second heartbeat, so a 10-second test was insufficient.

Active SSE shutdown hit Uvicorn's drain deadline before lifespan cleanup. This is not a passed
graceful SSE gate. The follow-up fix closes HTTP event streams before server drainage, preserving
internal MQTT subscriptions for final unavailable publications. A real loopback HTTP regression
test verifies normal chunked termination. Updated local results: 86 tests, 94.01 per cent coverage.
The Pi test API is currently stopped following the shutdown test. Next deliver the corrected
candidate and retest active SSE shutdown, then finish invalid-credential and physical recovery
checks. See `docs/v0.5.0-plan.md`. No release or later milestone is authorised by these partial gates.

### Soak milestone clarification, 6 September 2026

The user explicitly placed the extended, minimum 16-hour physical soak at v1.0.0. This
supersedes references to 12 hours in older handoff records. Continue earlier milestones without
waiting for the soak; do not interpret this as waiving v0.5.0 targeted recovery acceptance.
Record freshness, MQTT delivery, interruptions and unattended recovery during final soak testing.
The soak has not started or passed. The authoritative plan and physical acceptance document
have been updated accordingly.

### Leftover BlueZ connection recovery, 6 September 2026

Controlled API SIGKILL reproduced the overnight recovery symptom: BlueZ kept the registered
iGrill connected and the replacement API entered backoff with no readings. The original process
exit cause remains unknown. The follow-up candidate uses bounded, output-suppressed bluetoothctl
calls to release only the exact persisted identity when missing from discovery and still connected
in BlueZ. It then rediscovers and authenticates normally. No pairing removal or adapter reset.
Local checks pass 92 tests at 93.98 per cent coverage. Physical retest is pending; leave v0.5.0 open.
The Pi remains in the reproduced condition, awaiting the updated package and API restart without
hardware power cycling. The 16-hour soak remains a v1.0.0 gate.

### Recovery follow-up, 6 September 2026

The BlueZ-release candidate did not pass the physical abrupt-stop test. Isolated adapter
discovery/authentication/reading succeeded, and normal API startup then worked, but another
SIGKILL/restart failed. Do not claim recovery is fixed. A discovered cache-replacement race
is now covered by a regression test and fixed by holding one lock from candidate resolution
through connection and the first read. Protected diagnostics include a safe fixed-label
failureStage, with no raw exception content. Local checks: 93 tests, 94.01 per cent coverage.
Ship this follow-up and retest the existing condition without power cycling the iGrill.

### v0.5.0 acceptance and release handoff, 6 September 2026

The corrected recovery path passed controlled physical API SIGKILL plus manual process relaunch
without an iGrill power cycle or Bluetooth reset. Sequence advanced from 1 to 9, both probes
matched the display at 19 Celsius, battery 50 per cent, and two probes were absent. The original
overnight exit cause remains unknown. MQTT broker recovery, simulator restart/disconnect
persistence, invalid-credential retry and clean active-SSE/offline-MQTT shutdown also passed.

The Pi passed 93 tests at 94.01 per cent coverage, lint (67 formatted files) and strict typing
(42 sources). Final CI exposed a Python 3.11 MQTT cancellation hang, fixed using an asyncio
timeout context. Final CI run 34036122863 passed Python 3.11, 3.12 and 3.13; local checks also
passed 93 tests at 94.01 per cent. The Pi's installed build predates this last small MQTT change.
Deliver the final release package at the next update. Targeted v0.5.0 acceptance is complete.
Next milestone is v0.6.0 native installation, secure service account and automatic process restart.
The 16-hour soak is exclusively a v1.0.0 gate. Do not claim unattended long-cook readiness yet.

## v0.6.0 candidate handoff, 7 September 2026

v0.5.0 is released on GitHub, merged via PR 6 at a09096c98faf10c3e8b038e2d931de5ab62e6a0f.
The user authorised v0.6.0. Work is on codex/v0.6.0-native-deployment. Candidate implementation
adds deploy/manage.sh (install, backup, upgrade, rollback, non-destructive uninstall), a hardened
systemd unit, initial loopback/token-only YAML and a pitblu-state administrative CLI. The service
uses /opt/pitblu-core/current/venv with permanent root-owned versioned environments, configuration
under /etc/pitblu-core and protected state under /var/lib/pitblu-core. No existing test database
or Mosquitto configuration is imported or overwritten. Installer leaves the service stopped.

PITBLU_CONFIG_FILE selects explicit startup YAML; PITBLU_MANAGED=true refuses disabled auth or
a missing pre-bootstrapped token hash. Token bootstrap is interactive and must never be logged or
pasted into chat. Local results: 100 tests, 93.83 per cent coverage, Ruff (70 formatted files),
strict mypy (44 sources) and Bash syntax pass. Pi/systemd installation, recovery, backup/rollback
and permissions remain unverified; do not release v0.6.0 until those checks pass.

Deliver a source archive rooted at pitblu-core-v0.6.0/, separate from the running test source.
Use its own test virtual environment. The last known Pi test API remains on loopback port 8081;
do not reuse its historical PID without inspection. Production defaults to port 8080, loopback,
token authentication, physical BLE and MQTT disabled. Stop the test API before production device
onboarding to avoid competing BLE ownership. See docs/v0.6.0-plan.md and deployment procedures.

## v0.6.0 acceptance handoff, 7 September 2026

Native deployment acceptance passed. The Pi is now running the enabled pitblu-core systemd
service under the dedicated non-root account, not the earlier nohup test process. Production
API is loopback port 8080 with token authentication. Both physical probes matched 21 Celsius,
battery 50 per cent; MQTT publication and retained availability passed on a validation namespace.
No secrets, token values, private device addresses or protected database contents were recorded.

Tests: 100 passed, 93.83 per cent coverage, Ruff 70 files, strict mypy 44 sources and Bash syntax.
CI passes Python 3.11/3.12/3.13. Target checks covered HTTP 401, original-token authentication,
dedicated-account BLE, filesystem ownership/modes, systemd SIGKILL restart, Pi reboot recovery,
backup, same-candidate upgrade/rollback, non-destructive uninstall/unit restoration and continued
physical MQTT/readings. The local journal check found neither entered plaintext credential.
Cross-version migration, full security audit and soak are not implied by these checks.

Protected backups and previous releases remain on the Pi. The service was restored and is running
after uninstall testing. Do not use any historic PID; inspect systemctl for current state. Do not
start the old test API against the same thermometer. Keep the MQTT validation topic unchanged
until the user explicitly chooses to change it. Next planned milestone is v0.9.0: clean-Pi test,
security/documentation/provenance audits. The minimum 16-hour soak remains v1.0.0.

## Frontend integration handoff requirement: 7 September 2026

The user requires comprehensive documentation that another AI can use to build a
separate web-based application leveraging every exposed gateway capability.
`docs/frontend-integration.md` is the dedicated handoff, based on released v0.6.0
implementation behaviour. It inventories REST, authentication, configuration,
operations, SSE and MQTT, with payloads, client workflows and explicit limitations.
Keep it current in the same change as any public contract alteration. Do not imply
that OpenAPI alone describes the full response and behavioural contract.

`tests/test_frontend_documentation.py` checks that API routes, configuration keys
and canonical event types are covered. It is an inventory guard, not a semantic
proof. Local checks after this addition: 101 tests passed, 93.83 per cent coverage,
Ruff passed, 73 files formatted, mypy passed for 45 sources. Supported-Python CI
and the remaining v0.9.0 audits must still run for this branch.

The audit plan is `docs/v0.9.0-plan.md`. It records findings that must be resolved
or explicitly dispositioned, including PATCH label clearing, CORS response headers,
the unwired separate battery cadence and missing clock-health reporting. The
running Pi service has not been changed by this documentation work. Do not claim
v0.9.0 completion, a clean-Pi test or the v1.0.0 soak from these local checks.

### Plain-English companion guides

The user also requires documentation for an ordinary barbecue cook, alongside the
AI/developer handoff. Maintain `docs/bbq-overview.md` and `docs/bbq-quick-start.md`.
They explain what the gateway does, what still needs a separate application,
preparation and everyday use, and an optional read-only terminal check. Keep them
free of unnecessary jargon and do not imply that alarms, a dashboard, stored cook
history or the minimum 16-hour soak are already available or complete.
