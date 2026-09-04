# Architecture

The authoritative target is a native, headless Raspberry Pi gateway with separate control and
telemetry planes. Version 0.3.0 implements the REST control plane over the v0.2.0 device boundary.

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
policy models the planned 2, 4, 8, 15, 30 and 60-second schedule with plus or minus 20 per cent
jitter, while the future resilience controller remains v0.5.0 work.

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

SSE, MQTT, the resilience controller and systemd deployment remain later milestones. See the ADRs
under `docs/adr/`.
