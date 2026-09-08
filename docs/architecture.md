# Architecture

The authoritative target is a native, headless Raspberry Pi gateway with separate control and
telemetry planes. Released v0.6.0 implements both planes over the shared device boundary.

`DeviceAdapter` is the only device-facing boundary. The production and simulated V202 adapters
both implement asynchronous discovery, connection, disconnection and snapshot reads. Their shared
models carry one to four probe readings, battery state, UTC observation times, monotonic sequence
numbers and a physical or simulated source marker.

The discovery supervisor remains active but schedules finite scans. Its defaults are a five-second
scan, a 15-second interval while a device is missing and a 60-second background interval while an
adapter is connected. This is continuous supervision, not uninterrupted radio scanning.

Desired connection state is separate from the observed state. The observed states are discovered,
connecting, initialising, connected, polling, degraded, backoff, disconnected and unsupported.
Transitions are validated and repeated connect or disconnect requests are idempotent. The backoff
policy uses the 2, 4, 8, 15, 30 and 60-second schedule with plus or minus 20 per cent
jitter. Runtime recovery coordinates retries and stable-connection backoff reset.

FastAPI owns HTTP transport and generated OpenAPI. An administration service coordinates adapters
without coupling them to HTTP. SQLite contains registered devices, desired state, configuration
overrides, authentication hashes, secret values and bounded operation metadata. It never contains
temperature history. Live snapshots remain in memory.

Configuration precedence is default, YAML, environment and persisted override. A complete
Pydantic model validates the effective candidate before one SQLite transaction replaces persisted
overrides. Version ETags provide optimistic concurrency.

Authentication is optional only on loopback. Non-loopback binding requires bearer-token mode.
Only salted scrypt hashes are persisted for administrator tokens; rotation returns plaintext once.
Write-only integration secrets use dedicated endpoints and never appear in configuration or error
responses.

Successful snapshots enter `TelemetryState`, which owns current in-memory state and stale
deadlines. It emits immutable canonical events through a bounded `EventBus`. Recent REST history,
authenticated SSE subscribers and the optional MQTT publisher consume that same event type. Slow
subscribers have bounded queues and lose their oldest queued event rather than blocking device
sampling.

The MQTT adapter maps canonical events onto the independent `v1` topic contract. All publications
use QoS 1. Availability, connection and battery state are retained; temperature is not. Service
availability is protected by a retained Last Will. MQTT is disabled by default and has no command
subscription path.

The runtime serialises adapter calls and reserves one adapter owner. Registered desired
connections recover with jittered backoff and protected identity matching. Read failures degrade
state before sustained failure triggers reconnect. Startup marks interrupted operations and
restores eligible registrations. Operational events, but not telemetry history, are bounded in
SQLite. MQTT independently retries and exposes safe status. Shutdown cancels workers, preserves
desired state and flushes offline retained publications. Native systemd deployment provides
dedicated-account execution and automatic process restart. See [installation](installation.md)
and the [integration guide](frontend-integration.md) for current constraints.
