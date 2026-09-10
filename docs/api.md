# REST API

For a complete client-development handoff, see the
[frontend and AI integration guide](frontend-integration.md), including request and
response shapes, workflows, browser constraints and current implementation caveats.

The v0.9.0 release provides the administrative control plane and live telemetry stream. OpenAPI and interactive documentation
are generated at `/openapi.json` and `/docs`. The package default listens only on loopback.

## Authentication and errors

`GET /health` is always unauthenticated and returns only `{"status":"ok"}`. When `auth.mode` is
`token`, `/ready`, `/openapi.json`, `/docs`, `/redoc` and every `/api/v1/*`
resource require `Authorization: Bearer <token>`. Resource limits may return 429,
413 or 408; see the frontend guide for limits and retry behaviour.

Errors use one safe envelope with `code`, `message`, `correlationId` and optional redacted details.
The response repeats the correlation identifier in `X-Correlation-ID`. Request bodies and secret
values are never included in validation details.

## Resources

| Method and path | Result |
| --- | --- |
| `GET /health`, `GET /ready` | Minimal liveness and readiness. |
| `GET /api/v1/status` | Service version, status and UTC time. |
| `GET /api/v1/diagnostics` | Safe MQTT and device-worker status, failure codes and session ID. |
| `GET /api/v1/events/operations` | Up to 100 persistent operational/configuration events. |
| `GET /api/v1/bluetooth` | Adapter availability, connection and physical/simulated source. |
| `POST /api/v1/scans` | Starts a scan operation and returns HTTP 202. |
| `GET /api/v1/scans/{scanId}` | Operation state and supported temporary discovery results. |
| `GET`, `POST /api/v1/devices` | Lists or registers explicitly selected devices. |
| `GET`, `PATCH`, `DELETE /api/v1/devices/{deviceId}` | Manages one registered device. |
| `POST /api/v1/devices/{deviceId}/{action}` | Starts `connect`, `disconnect` or `reconnect`; HTTP 202. |
| `GET /api/v1/devices/{deviceId}/probes` | Current probe state, including freshness. |
| `GET /api/v1/devices/{deviceId}/battery` | Current battery state, including freshness. |
| `GET /api/v1/operations[/{operationId}]` | Up to 100 recent persistent operation records. |
| `GET /api/v1/events` | Up to 100 recent canonical telemetry events. |
| `GET /api/v1/events/stream` | Live canonical events as `text/event-stream`. |
| `GET`, `PATCH /api/v1/config` | Describes or transactionally updates effective settings. |
| `GET /api/v1/config/schema` | Setting metadata and write-only secret status. |
| `POST /api/v1/config/validate` | Validates a proposed whole configuration without saving it. |
| `PUT`, `DELETE /api/v1/config/secrets/{name}` | Sets or removes an allowed write-only secret. |
| `POST /api/v1/auth/token/rotate` | Invalidates the old token and returns its replacement once. |

Registration accepts the opaque `discoveryId` from an authenticated scan response, an optional
`friendlyName`, `connect`, and `automaticReconnection`. This avoids putting a Bluetooth address in
ordinary REST payloads. A stable public `deviceId` is assigned and persisted.

Operation status is `queued`, `running`, `succeeded` or `failed`. Failures contain a stable safe
error code, never a raw Bleak error or address. API reads and repeated connection
requests are idempotent in their resulting state. An identical pending control returns its existing
operation. A conflicting pending control returns HTTP 409. Scan, connect, read and disconnect calls
share an adapter lock. Another registered device cannot acquire an already-owned adapter.

Registrations store protected hardware identity separately from public fields.
Automatic recovery never guesses identity from an advertised name. Registered
desired state and automatic-reconnection preference determine startup recovery. The current service restores one adapter owner at a time.

`/health` is only liveness. With MQTT enabled, `/ready` returns 503 until the publisher connects.
Diagnostics contain safe codes rather than exception messages, host settings or credentials.

SSE frames contain `id`, `event` and JSON `data` fields. The data is the same canonical schema used
by recent history and, where applicable, MQTT: `schemaVersion`, `eventId`, `type`, `observedAt`,
`sequence`, `source`, `sessionId`, optional `deviceId` and `probe`, and type-specific `data`. Idle streams send
comment heartbeats at the configured availability-heartbeat interval. Authentication follows the
same rules as all other `/api/v1/*` resources.

After the stale threshold, probe and battery resources keep their last observation metadata but
return `fresh: false`; stale temperatures and battery percentages are returned as `null`.
