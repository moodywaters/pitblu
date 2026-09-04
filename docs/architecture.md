# Architecture

The authoritative target is a native, headless Raspberry Pi gateway with separate control and
telemetry planes. Version 0.1.0 intentionally implements neither plane. Its only executable path is
a short-lived physical proof, separated into hardware-independent protocol decoding and a
Bleak-based orchestration module.

Later milestones will place Bleak behind an internal device-adapter interface before adding state
management, FastAPI, SQLite, SSE, MQTT or systemd deployment. See
`docs/adr/0001-incremental-hardware-first.md`.

