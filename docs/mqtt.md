# MQTT

See the [frontend integration guide](frontend-integration.md) for every payload type,
SSE differences and subscriber reconciliation rules. In particular, service
availability reuses sequence values and must not use device-telemetry deduplication.

For normal terminal setup, run `pitblu-core-config mqtt`; it validates the same settings described
below and keeps the password on a hidden, write-only path.

The v0.9.0 release publishes telemetry to MQTT when `mqtt.enabled` is true. MQTT is a read-only data
plane: the service does not subscribe to or accept administrative commands. The default broker is
local, but host, port, TLS, username and base topic are configurable. The password is managed only
through the write-only secret API.

## Topic contract

With the default `pitblu` base topic:

| Topic | Retained |
| --- | --- |
| `pitblu/v1/service/availability` | Yes, with Last Will |
| `pitblu/v1/devices/{deviceId}/availability` | Yes |
| `pitblu/v1/devices/{deviceId}/connection` | Yes |
| `pitblu/v1/devices/{deviceId}/battery` | Yes |
| `pitblu/v1/devices/{deviceId}/probes/{probe}/availability` | Yes |
| `pitblu/v1/devices/{deviceId}/probes/{probe}/temperature` | No |

Every publication uses QoS 1 and JSON. Consumers must tolerate duplicate delivery and can
deduplicate device telemetry by session, topic and sequence. Service availability reuses
sequence values; use the integration guide's arrival-order rules instead. Device topics contain a stable
public identifier, never a Bluetooth address. Probe numbers are one-based.

A temperature payload is shaped as follows:

```json
{
  "schemaVersion": 1,
  "deviceId": "igrill-v202-example",
  "probe": 1,
  "temperatureC": 20.5,
  "observedAt": "2026-09-05T12:00:00+00:00",
  "sequence": 42,
  "sessionId": "<process session>",
  "source": "physical"
}
```

Availability, connection and battery payloads use the same envelope and add their state fields.
The service publishes retained online state after connecting to the broker and configures a
retained unavailable Last Will before connecting. A normal publisher stop also publishes the
unavailable state.

The Last Will payload is prepared before connecting. Its `observedAt` is therefore the preparation
time, not the eventual disconnect time. Consumers should record their own receipt time for failure
detection. Device sequence counters are scoped to the running process and topic; they reset on restart.

Publisher failures enter retry backoff using base delays of 2, 4, 8, 15, 30 and 60 seconds with
20 per cent jitter. Backoff resets after a stable connection, not after every connection attempt.
`GET /api/v1/status` and `/api/v1/diagnostics` expose MQTT state, failure count and a safe error code.
`/ready` returns 503 while enabled MQTT is not connected; `/health` remains process liveness only.
An idle connection is checked by the configured availability heartbeat; loss can be detected on
the next publish, including that heartbeat. Broker delivery remains part of manual acceptance.

On reconnection the publisher restores the latest retained device, connection, battery and probe
state. It does not replay temperature history. Normal shutdown flushes current offline state and
publishes service unavailability with a current timestamp. Last Will timestamps still represent
preparation time. Every process has a `sessionId`, shared by its SSE and MQTT telemetry; consumers
should combine it with topic and sequence when identifying samples across process restarts.

Temperatures are deliberately not retained. Current state is available through REST, and an active
subscriber receives subsequent readings at the configured probe polling interval. When no fresh
snapshot arrives before `polling.stale_after`, device and probe availability events report
`available: false` with reason `stale`; REST suppresses the old numeric values.
The retained battery state is also invalidated with a null percentage. Explicit disconnect
invalidates available state immediately.

Do not put credentials in YAML, shell history or source control. Configure `mqtt.password` through
the authenticated write-only secret endpoint. Additional consumers should use separate
least-privilege broker identities.
