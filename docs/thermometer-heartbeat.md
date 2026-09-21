# Thermometer communication heartbeat

The thermometer heartbeat answers one question: **has pitblu-core successfully
communicated with this registered thermometer recently?** It is live, observational
state. It does not cause reconnection and it is not persisted across a service restart.

## What counts

A heartbeat advances only after a validated thermometer exchange: completed model-
specific initialisation/authentication, a decoded probe read, or a decoded battery
read. A valid "probe not inserted" response counts because the thermometer replied.
A BLE link, Bluetooth adapter power, polling timer, cached battery value, failed GATT
read, or snapshot containing only failures does not count.

These layers prove different things:

```text
pitblu-core process health        /health says the process can answer HTTP
        |
transport health                  SSE/MQTT can carry messages
        |
Bluetooth adapter                 the host radio is available
        |
device connection                 the BLE connection workflow has a state
        |
thermometer heartbeat             the thermometer recently answered successfully
        |
probe freshness                   a particular probe value is current
```

SSE `: heartbeat` comments only keep the HTTP stream open. MQTT service availability
and its Last Will report the core service, not the thermometer. None of those advances
the thermometer heartbeat.

## States

- `unknown`: no successful thermometer communication in this service session.
- `healthy`: success occurred within `polling.thermometer_heartbeat_stale_after`.
- `stale`: the most recent success is older than that threshold.
- `disconnected`: the operator explicitly requested a disconnected desired state.

Connection states remain separate. `degraded` means repeated polling failures;
`backoff` means automatic recovery is waiting; `connecting` and `initialising` mean an
attempt is active. A battery exchange can keep communication healthy while probe reads
are failing, so a healthy heartbeat and degraded probe sampling can briefly coexist.

With no probes inserted, successful no-probe replies keep the heartbeat healthy while
each probe reports `present: false`. If all recognised GATT reads fail, the timestamp
does not move, the heartbeat ages to stale, and the existing connection state machine
may independently progress through degraded and backoff.

## Check and recover

Run the canonical local support command:

```console
$ pitblu-core-config check
Thermometer
[PASS] Device Patio iGrill: desired=connected, observed=polling
[PASS] Communication Patio iGrill: last succeeded 4 seconds ago
[PASS] Probes Patio iGrill: 4 fresh reading(s)
```

A failure can look like:

```text
[WARN] Device Patio iGrill: desired=connected, observed=backoff
[FAIL] Communication Patio iGrill: stale; last succeeded 42 seconds ago
[WARN] Recovery Patio iGrill: automatic recovery is active
```

Normally, wait for automatic recovery. To bypass the current backoff and request an
immediate attempt, use:

```console
$ pitblu-core-config igrill reconnect
```

An optional registered device ID may follow `reconnect`. The command posts to the
existing REST reconnect endpoint, polls the returned operation, and then refreshes
device, heartbeat, probe, and battery state. HTTP 202 means accepted only. The command
reports success only after the operation succeeds and recent communication is
confirmed. It never connects to Bluetooth directly or prints a native Bluetooth
address. Explicit disconnect still cancels automatic recovery; reconnect later only
when that is intentional.

## REST

Device list and detail responses contain:

```json
"heartbeat": {
  "status": "healthy",
  "lastSuccessfulCommunicationAt": "2026-09-21T14:32:10.482000+00:00",
  "fresh": true,
  "staleAfterSeconds": 15.0,
  "sequence": 27,
  "source": "physical",
  "sessionId": "4dc3..."
}
```

The timestamp and source are null before the first success. `fresh` is always Boolean.
Age is deliberately not serialized because it would become obsolete in a cached
response; calculate it from the timestamp. Sequence is per device and per service
session. A restart changes `sessionId`, resets the timestamp to null, and reports
unknown until new communication succeeds. Desired and observed device state remain in
their existing fields.

`POST /api/v1/devices/{deviceId}/reconnect` returns an asynchronous operation with
HTTP 202. Poll `GET /api/v1/operations/{operationId}` to a terminal state, then refetch
the device. `succeeded` means the existing adapter connection and initialisation path
completed; consumers should still display the refreshed heartbeat truth.

## SSE

`thermometer.heartbeat` uses the normal version-one event envelope. It is emitted for
each new success and for transitions to stale, disconnected, or new-session unknown.
The event `observedAt` describes that success or state transition; its data contains
`status`, `lastSuccessfulCommunicationAt`, `fresh`, and `staleAfterSeconds`.

This is different from an SSE `: heartbeat` comment, which has no telemetry meaning.
There is no guaranteed replay. On initial connection or SSE reconnection, fetch device
REST state, buffer events during the fetch, then apply only events from the current
session with newer sequence. A stale event never requests recovery.

## MQTT

The retained QoS 1 topic is:

```text
{baseTopic}/v1/devices/{deviceId}/heartbeat
```

Its payload contains `schemaVersion`, `observedAt`, `sequence`, `source`, `sessionId`,
`deviceId`, and the heartbeat data fields. On startup pitblu-core publishes unknown for
registered devices, replacing older retained state. Consumers must still require the
current retained service availability to be online, compare session IDs, and evaluate
the timestamp. A retained heartbeat is historical state, not proof the process is
alive. MQTT service availability and Last Will remain the service-health authority.

## Maintainer model

Adapters are the evidence boundary. They timestamp only recognised, validated
exchanges. `TelemetryState` is the in-memory source of current heartbeat state, owns
the stale deadline, and maps it to REST and canonical events. SSE and MQTT consume
those events. SQLite never stores heartbeat state.

The heartbeat observes; `AdministrationService` and its existing state machine own
recovery; the operator may invoke the existing reconnect operation. Never add
`heartbeat stale -> reconnect` to telemetry code. A future thermometer adapter must
document its model-specific successful operations, return explicit communication
evidence, test no-response and no-probe cases, and never infer success from a timer or
connection flag.

Automated tests cover evidence, ageing, event and transport mappings, session reset,
simulation, recovery boundaries, CLI operation polling, and sanitisation. Real Pi and
iGrill validation remains a separate v1.0.0 physical gate.
