# ADR 0008: thermometer communication heartbeat

Status: accepted for implementation, 21 September 2026.

## Decision

Represent recent thermometer communication as explicit evidence produced by the
device adapter and current state owned by `TelemetryState`. Successful authenticated
initialisation and successfully decoded probe or battery reads count. A valid absent-
probe sentinel counts; connection flags, timers, cached values, and failed reads do
not. State is session-scoped and is not persisted.

Expose the state as the embedded REST `heartbeat` object, the canonical
`thermometer.heartbeat` event, and the retained MQTT device `heartbeat` topic. Use a
dedicated `polling.thermometer_heartbeat_stale_after` threshold. Preserve the existing
connection state machine as the sole automatic-recovery owner and the existing REST
reconnect operation as the sole operator force-recovery path.

## Consequences

Consumers can distinguish a live process, live transport, powered adapter, BLE state,
responding thermometer, and fresh probe. Retained MQTT state requires session and
service-availability checks. Restart begins at unknown. Adapters must explicitly
declare communication evidence, but future models can choose their own validated
protocol operations without changing the external contract.
