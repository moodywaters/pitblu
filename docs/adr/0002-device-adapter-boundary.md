# ADR 0002: Isolate devices behind one asynchronous boundary

- Status: accepted
- Date: 4 September 2026

Historical decision context: statements about later milestones below describe the
decision date. The resilience controller is now implemented; consult the
[current architecture](../architecture.md) for present behaviour.

## Decision

Represent physical and simulated thermometers through the same internal `DeviceAdapter` protocol.
The boundary owns discovery, connection, disconnection and snapshot reads. Canonical models, not
Bleak objects, cross it. Native discovery objects remain private to the production adapter and are
addressed externally only by short-lived opaque identifiers.

Keep desired and observed connection state in a separate explicit state machine. Keep scheduled
discovery separate from both the adapter and state machine.

## Consequences

Later control and telemetry layers can consume one typed interface and distinguish physical from
simulated readings. Hardware-independent tests exercise the same models as production. Bluetooth
addresses are not required in public models, logs or fixtures.

The adapter completes transport connection and Weber authentication as one bounded operation. A
future resilience controller will coordinate polling, stable-connection timing and automatic retry;
that controller remains outside the v0.2.0 scope.
