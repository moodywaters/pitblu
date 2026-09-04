# Architecture

The authoritative target is a native, headless Raspberry Pi gateway with separate control and
telemetry planes. Version 0.2.0 intentionally implements neither external plane. It supplies the
device foundation that later service layers will consume.

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

FastAPI, SQLite, SSE, MQTT and systemd deployment remain later milestones. See
`docs/adr/0001-incremental-hardware-first.md` and `docs/adr/0002-device-adapter-boundary.md`.
