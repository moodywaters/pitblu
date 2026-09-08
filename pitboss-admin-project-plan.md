# PitBoss Admin Project Plan

Status: authoritative target specification; implementation released through v0.6.0.

Documentation status reviewed: 7 September 2026.

This specifies intended scope, not proof that every feature or release gate is
complete. Use the [documentation index](docs/README.md) and
[frontend guide](docs/frontend-integration.md) for current released behaviour.
The v0.9.0 audit and v1.0.0 final physical gates remain pending.

## Objective

Build `pitboss-admin`, a headless, API-first service running on a Raspberry Pi that discovers, connects to and monitors a Weber iGrill over Bluetooth Low Energy. It exposes all administrative and operational functionality through a REST API and publishes reusable telemetry through MQTT.

The later PitBoss web application is a separate project. It will consume the API and MQTT data and provide cook sessions, history, graphs, alarms and other user-facing features.

## Confirmed environment

- Raspberry Pi 4 Model B Rev 1.4
- Raspberry Pi OS build dated 18 June 2026
- Debian GNU/Linux 13.5 Trixie base
- 64-bit ARM (`aarch64`)
- Python 3.13.5
- BlueZ 5.82
- Onboard Bluetooth adapter `hci0`, powered and unblocked
- Hostname: `pitboss`
- Ethernet currently preferred over Wi-Fi
- Native installation managed by `systemd`
- Docker explicitly excluded

## Confirmed iGrill hardware

- Advertised device: Weber `iGrill_V202-CD09`
- Variant: iGrill V202, part of the iGrill 2 family
- Four probe capability expected
- BLE discovery works from the Raspberry Pi
- Direct BlueZ connection succeeds and exposes standard Battery Service and Weber vendor-specific GATT services
- A basic `bluetoothctl` connection does not remain active after discovery stops, indicating that the application must perform the Weber-specific initialisation/authentication sequence
- The Bluetooth address is private deployment configuration and must never be committed to GitHub

## Architecture

### Control plane

REST API is the sole administrative control plane. It owns:

- Bluetooth scanning and discovery
- Device registration and removal
- Connect, disconnect and reconnect requests
- Desired and observed connection state
- Runtime configuration
- Health, readiness and diagnostics
- Asynchronous operation tracking
- Recent operational events

Administrative commands will not be accepted over MQTT.

### Data plane

MQTT carries reusable telemetry and availability information:

- Raw probe temperatures in Celsius
- Probe presence and availability
- iGrill availability and connection state
- Battery percentage
- Service availability using MQTT Last Will and Testament
- UTC observation timestamps
- Sequence numbers
- Physical or simulated source indicator

SSE may mirror live events for browser clients. REST remains the command channel.

### MQTT contract

The default base topic is `pitboss`, but it is configurable. MQTT schema version `v1` is independent of the REST API version.

- `pitboss/v1/service/availability`
- `pitboss/v1/devices/{deviceId}/availability`
- `pitboss/v1/devices/{deviceId}/connection`
- `pitboss/v1/devices/{deviceId}/battery`
- `pitboss/v1/devices/{deviceId}/probes/{probeNumber}/availability`
- `pitboss/v1/devices/{deviceId}/probes/{probeNumber}/temperature`

All payloads are JSON. Temperature payloads contain `schemaVersion`, `deviceId`, one-based `probe`, numeric `temperatureC`, UTC `observedAt`, monotonically increasing `sequence`, and `source` set to `physical` or `simulated`. Bluetooth addresses never appear in topics or ordinary payloads.

All version-one publications use QoS 1, so consumers must tolerate duplicate delivery and may deduplicate using sequence numbers. Service, device, connection, battery and probe-availability topics are retained. Temperature topics are not retained, preventing stale temperatures from appearing current and avoiding unnecessary retained writes to Raspberry Pi storage. Current temperature state remains available through REST, and active MQTT consumers receive the next sample within the polling interval.

The retained service-availability topic uses MQTT Last Will and Testament. No administrative commands are accepted over MQTT. A consumer can subscribe to all temperature readings using `pitboss/v1/devices/+/probes/+/temperature`.

### Internal design

- Python 3.11+ compatible implementation, tested on Python 3.13
- FastAPI with generated OpenAPI specification and interactive documentation
- Bleak-based Bluetooth implementation behind an internal device-adapter interface
- Explicit per-device connection state machine
- SQLite for administrative state only
- Structured logging to `journald`

## Version one scope

### Bluetooth and devices

- Continuous BLE discovery
- Explicit Weber iGrill V202/iGrill 2 support
- Up to four probe channels
- Probe insertion and removal detection
- Battery readings
- Configurable scan, connect, initialisation and read timeouts
- Exponential reconnection backoff with jitter
- Clean recovery after connection loss
- Stable public device identifiers separate from Bluetooth addresses
- Persistent desired connection state
- Graceful connection and service shutdown
- Documented behaviour when the official Weber application competes for the BLE connection

### Device onboarding contract

- Automatic connections are permitted only for devices explicitly registered by the user
- A frontend starts discovery, displays supported devices, and lets the user select one
- `POST /api/v1/devices` accepts the discovered Bluetooth address, optional friendly name, initial connect choice and automatic-reconnection choice
- Registration assigns a stable public device identifier, for example `igrill-v202-cd09`
- Normal REST URLs, responses and MQTT topics use the stable identifier rather than the Bluetooth address
- The Bluetooth address remains protected deployment data and is excluded from ordinary logs, diagnostics and source control
- An add-and-connect request may register the device and immediately begin an asynchronous connection operation
- Registered devices retain their desired connection state across service restarts
- Nearby unregistered Weber devices may appear in temporary discovery results but are never connected automatically

### REST API

- Versioned under `/api/v1`
- OpenAPI document and interactive `/docs`
- Health and readiness endpoints
- Bluetooth adapter and discovery endpoints
- Discovered-device and managed-device endpoints
- Connect, disconnect and reconnect operations
- Probe and battery state endpoints
- Asynchronous operation resources with correlation identifiers
- Idempotent control operations
- Serialised operations per device
- Recent bounded operational event history
- Bearer-token authentication
- CORS disabled by default and explicitly configurable

### REST resource contract

- Minimal unauthenticated liveness: `GET /health`
- Minimal readiness: `GET /ready`
- Authenticated operational summary: `GET /api/v1/status`
- Bluetooth state: `GET /api/v1/bluetooth`
- Discovery: `POST /api/v1/scans` and `GET /api/v1/scans/{scanId}`
- Managed collection: `GET /api/v1/devices` and `POST /api/v1/devices`
- Managed device: `GET`, `PATCH` and `DELETE /api/v1/devices/{deviceId}`
- Connection commands: `POST /api/v1/devices/{deviceId}/connect`, `/disconnect` and `/reconnect`
- Current telemetry: `GET /api/v1/devices/{deviceId}/probes` and `/battery`
- Asynchronous work: `GET /api/v1/operations` and `GET /api/v1/operations/{operationId}`
- Operational history: `GET /api/v1/events`
- Live event stream: `GET /api/v1/events/stream`
- Configuration: `GET` and `PATCH /api/v1/config`, `GET /api/v1/config/schema`, and `POST /api/v1/config/validate`
- Write-only secrets: `PUT` and `DELETE /api/v1/config/secrets/{secretName}`

Slow operations return HTTP `202 Accepted` with an operation identifier. Resource creation returns `201 Created`. Validation errors use `422`, state conflicts use `409`, and authentication or authorisation failures use `401` or `403`. Errors share one JSON envelope containing a stable error code, human-readable message, correlation identifier and optional safe details. Read operations and repeated connect/disconnect requests are idempotent.

`/health` reveals only non-sensitive process liveness without authentication. All other endpoints require authentication when network access is enabled. SSE uses the canonical internal event schema shared with the operational event log and, where applicable, MQTT.

### Configuration API

Every application-level setting must be represented through REST. A future frontend must be able to configure normal application behaviour without SSH or direct file editing.

The configuration API must expose:

- Effective value
- Source, such as default, YAML, environment or persisted override
- Type and description
- Default, minimum, maximum and allowed values
- Whether the field is editable
- Whether a restart is required
- Whether the value is sensitive
- Configuration version or ETag

Updates must be validated and persisted transactionally. Conflicting concurrent updates must be rejected. Secrets are write-only and must never be returned through REST or logs. Deployment-level settings such as filesystem paths and the Linux service account may be startup-only or read-only.

MQTT configuration must support local, remote and hosted brokers, optional TLS, authentication, configurable topics and MQTT-disabled API-only operation.

### Reliability and data integrity

- Raw decoded temperature values, without smoothing
- Invalid and sentinel-value rejection
- Fresh and stale state for every reading
- Separate service, device and probe availability
- UTC ISO 8601 timestamps
- Clock-synchronisation awareness
- Configurable heartbeat without needless duplicate telemetry
- Graceful MQTT reconnection
- Bounded logs and operational event history
- Safe duplicate-request and concurrency handling

### Version-one timing defaults

All values are typed, validated and configurable through the configuration API.

- BLE scan duration: 5 seconds
- Scan interval while the desired device is missing: 15 seconds
- Background scan interval while connected: 60 seconds
- Connection timeout: 10 seconds
- GATT initialisation timeout: 15 seconds
- Individual BLE read timeout: 5 seconds
- Probe polling interval: 5 seconds
- Battery polling interval: 300 seconds
- Reading stale threshold: 15 seconds
- Connection degraded after: 3 consecutive failed polling cycles
- Forced reconnect after: 30 seconds without a valid reading
- Availability heartbeat: 60 seconds
- Stable connection period before backoff reset: 60 seconds
- Reconnection delays: 2, 4, 8, 15, 30 and then 60 seconds maximum
- Reconnection jitter: plus or minus 20 per cent
- An authenticated REST reconnect request bypasses the current backoff delay

Continuous discovery means the discovery supervisor remains active, not that the radio scans without interruption. Scanning is scheduled to limit radio activity and reduce interference with an active BLE connection.

### Simulation and testing

- Built-in simulated iGrill mode, disabled by default
- One to four simulated probes
- Rising, falling and stable temperature patterns
- Simulated insertion, removal, battery changes and connection failures
- Unit tests for temperature and payload decoding
- Recorded BLE payload fixtures
- Connection state-machine, timeout and backoff tests using controlled time
- API contract tests
- MQTT publishing and failure tests
- Graceful shutdown tests
- GitHub Actions for formatting, linting and hardware-independent tests
- Separate physical iGrill acceptance checklist

### Native deployment

- Dedicated low-privilege Linux service account
- Application and virtual environment under `/opt/pitboss-admin/`
- Non-secret configuration under `/etc/pitboss-admin/`
- Protected secret environment file
- Administrative state under `/var/lib/pitboss-admin/`
- `systemd` startup, restart and shutdown behaviour
- `journald` logging
- Documented install, upgrade, backup, rollback and uninstall procedures
- No automatic updates during an active cook

## Local MQTT broker

Mosquitto is installed locally on `pitboss` and has been tested successfully.

Current broker design:

- TCP listener on port 1883
- IPv4 and IPv6 listeners
- Anonymous access disabled
- Password authentication enabled
- `pitboss-admin` MQTT identity
- ACL limited to `pitboss/#`
- Retained publish and subscription tested
- Broker location remains configurable in the application

The local broker is the deployment default, not a hard-coded dependency. Additional read-only client identities should be created later for Node-RED and the future web application.

## Security principles

- Never expose the API or MQTT broker directly to the internet
- Localhost and trusted-LAN modes
- Authentication required for network control
- No arbitrary operating-system command endpoint
- Rate limiting for disruptive operations
- Secrets excluded from API responses, logs, diagnostic exports and GitHub
- Unrelated nearby Bluetooth device details excluded from normal logs
- Correlation identifiers connect API requests, operations and log entries

### API authentication and exposure contract

- Default API port: 8080, configurable
- Installed trusted-LAN deployment binds to `0.0.0.0`; loopback-only mode binds to `127.0.0.1`
- Bearer-token authentication is required whenever the service is reachable beyond loopback
- `GET /health` is unauthenticated and returns only minimal liveness, such as `{"status":"ok"}`
- `GET /ready` and all `/api/v1/*` endpoints require authentication in trusted-LAN mode
- Installation generates a cryptographically secure initial administrator token and displays it once
- Only a secure token hash is persisted; the plaintext token is never logged or committed
- An authenticated API operation can rotate the administrator token; the replacement is returned once
- `auth.mode: disabled` is permitted only with loopback binding
- Configuration validation rejects an unauthenticated non-loopback bind
- Version one does not implement built-in HTTPS
- Plain HTTP is documented as trusted-LAN only and must never be exposed directly to the internet
- A future web application stores the token in its backend; Node-RED stores it as a protected credential
- Reverse-proxy and TLS support can be added later without changing the REST contract

## GitHub and documentation

- Repository: `pitboss-admin`
- Owner: John's personal GitHub account
- Initially private
- May be made public later
- MIT is the provisional project licence, subject to final dependency and source review
- GitHub Issues, milestones, feature branches, pull requests and releases
- Semantic versions and maintained `CHANGELOG.md`
- Architecture Decision Records for significant choices
- Dependabot and automated CI
- No personal configuration, credentials, network addresses or Bluetooth addresses committed

Required documentation includes architecture, REST API, configuration schema, Bluetooth behaviour, MQTT topics and payloads, native installation, operation, upgrade, rollback, troubleshooting, development and physical acceptance testing.

## Third-party provenance

The public repository must contain `THIRD_PARTY_NOTICES.md` and `docs/provenance.md`.

Every external dependency, copied fragment, substantially adapted implementation, protocol reference and significant architectural influence must be categorised accurately. Before copying or adapting source, inspect its exact licence and relevant file history. Record the repository, commit, licence, copyright, affected component and nature of modifications in the same change that introduces it.

Current research references:

- `jaydenk/igrill-remote-server`, modern Python BLE lifecycle and resilience reference
- `bendikwa/esphome-igrill`, Weber iGrill protocol and device-support reference
- `pilot1981/weber-igrill-integration-HA`, historical Raspberry Pi MQTT bridge reference
- `1mckenna/esp32_iGrill`, MQTT and device-behaviour reference
- `sanjay900/igrill`, Home Assistant and pairing-behaviour reference

`elupus/togrill-bluetooth` is not a Weber iGrill library and is explicitly excluded.

## Explicitly outside version one

- Cook sessions and temperature history
- Cook database
- Graphs and dashboards
- Food names and probe roles
- Timers and target-temperature alarms
- User notifications
- Completion-time forecasting
- Browser user interface
- Administrative MQTT commands
- Direct internet exposure
- Docker and container deployment

## Decisions still to complete

- Exact REST API resources and response contracts
- MQTT topic and payload contract, QoS and retention rules
- Default polling, battery and stale-data intervals
- API port, bind behaviour and authentication bootstrap
- Whether SSE is mandatory in version one
- Multi-iGrill behaviour in version one versus forward-compatible design only
- Repository creation timing
- Physical acceptance criteria
- Final third-party licence review and project licence confirmation

## Version 1.0 physical release gates

### iGrill hardware

- Discover the physical V202 within 20 seconds
- Register and connect it entirely through REST, without `bluetoothctl`
- Resolve the correct Weber GATT services
- Detect all four probe channels when inserted
- Report Celsius temperatures within 1 degree Celsius of the iGrill display
- Detect probe removal within 15 seconds
- Return battery percentage
- Reject known invalid and sentinel temperatures

### Recovery

- Mark readings stale within 15 seconds of data loss
- Publish device and probe unavailability correctly
- Recover automatically after the iGrill is switched off and on
- Recover from a temporary Bluetooth failure without restarting the service
- Recover automatically after Mosquitto restarts
- Restore persisted desired connection state after Raspberry Pi reboot
- Complete an at-least-16-hour physical soak test without manual intervention
- Record and automatically recover any transient disconnection during the soak

### API and MQTT

- Every agreed administrative and operational function works through REST
- Long-running operations return and update an operation resource
- SSE delivers readings and state transitions using the canonical event schema
- MQTT topics and payloads conform to the version-one contract
- MQTT Last Will behaviour is verified
- Anonymous API access and unauthorised MQTT access are rejected
- Configuration updates validate, persist and survive reboot
- Secrets never appear in responses, logs or diagnostic exports
- Simulated and physical readings are always distinguishable

### Deployment and publication readiness

- Clean native installation succeeds on the confirmed Raspberry Pi 4 and Raspberry Pi OS Trixie environment
- The `systemd` service starts automatically and shuts down gracefully
- Graceful shutdown publishes correct availability state
- Upgrade and rollback procedures are tested
- Hardware-independent tests pass in GitHub Actions
- Documentation is sufficient to repeat installation on a clean Pi
- Third-party provenance, notices and licence obligations are complete

These are mandatory gates for `v1.0.0`. Earlier `v0.x` milestone releases may be published while the gates are being completed.

## Planned output

Once these decisions are complete, produce a detailed implementation prompt for ChatGPT Codex. The prompt must require incremental development, documentation in the same changes as code, tests, provenance tracking, native Raspberry Pi deployment and explicit validation against the physical Weber iGrill V202.

## Locked implementation milestones

- `v0.1.0`: repository scaffold, licence review, CI, documentation structure, and a focused physical BLE spike that connects to the V202 and reads at least one probe plus battery
- `v0.2.0`: production iGrill adapter, continuous discovery, four probes, connection state machine, simulator and recorded BLE fixtures
- `v0.3.0`: REST resources, asynchronous operations, authentication and complete configuration API
- `v0.4.0`: MQTT contract, Last Will, SSE stream and stale-data handling
- `v0.5.0`: reconnection resilience, persistence, concurrency controls, diagnostics and graceful shutdown
- `v0.6.0`: native installer, dedicated service account, filesystem permissions, `systemd`, upgrade and rollback
- `v0.9.0`: clean-Pi installation test, security review, documentation audit and third-party provenance audit
- `v1.0.0`: complete physical acceptance suite and successful at-least-16-hour soak test

Codex must complete and verify each milestone before advancing. The physical BLE spike comes first so that the proprietary hardware interaction is proven before the surrounding service is built.

The architecture plan is complete. The master implementation prompt is maintained separately as `pitboss-admin-codex-prompt.md`.
