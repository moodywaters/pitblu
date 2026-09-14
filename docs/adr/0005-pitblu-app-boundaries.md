# ADR 0005: pitblu-app platform and service boundaries

**Status:** Accepted

## Context

Pitblu separates physical thermometer integration from cooking intelligence. A
common deployment may place both services on a Raspberry Pi, but treating that host
choice as application architecture would couple cook capabilities to one operating
system and make independent scaling or relocation needlessly difficult. The cook
model must also remain valid for more than one thermometer and more than four total
probe sources.

## Decision

`pitblu-core` owns thermometer discovery, Bluetooth, device lifecycle, current
physical telemetry and its REST/SSE contracts. It remains a focused thermometer
gateway rather than a generic hardware platform.

`pitblu-app` owns cooks, semantic measurements, time-bound assignments, history,
targets, alerts, events, lifecycle and client-facing APIs. It is platform-neutral
and communicates with pitblu-core only over REST/SSE through the concrete
`PitbluCoreClient` behind the `ThermometerGateway` boundary. It does not import core
implementation modules, access core storage, use MQTT as a duplicate input, or
depend on GPIO, BLE, BlueZ, ARM, Raspberry Pi OS or systemd.

A physical source is identified by `(core device ID, probe channel)`. Channels are
not globally unique, cooks do not belong to one mandatory device, and measurements
and assignments are collections. A time-bound assignment captures semantic meaning
when a reading is stored, so later reassignment cannot rewrite history.

Future blower control, if built, belongs to the independent sibling service
`pitblu-blower-core`. Its real-time control loop, safety behavior and hardware
lifecycle stay outside pitblu-core, pitblu-app and browser code. A concrete blower
client may later sit beside the thermometer client without changing Cook entities.
No generic provider registry, plugin bus or speculative actuator hierarchy is
introduced now.

All meaningful behavior is exposed through pitblu-app's versioned backend API.
Official browser clients, integrations and future physical controls use the same
capabilities; the UI owns presentation state only.

## Consequences

- The application can run anywhere its Python runtime, database and network access
  are available.
- Linux/systemd and Raspberry Pi files are optional deployment examples only.
- Multiple devices and variable probe counts require no schema change.
- Additional independent service adapters can be added at the application-service
  boundary without generalising pitblu-core or rewriting the Cook domain.
