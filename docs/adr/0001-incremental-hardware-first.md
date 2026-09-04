# ADR 0001: Prove the proprietary BLE path first

- Status: accepted
- Date: 4 September 2026

## Decision

Build only a focused, disposable-quality-but-tested BLE spike in v0.1.0. Do not build the service
layers until the target V202 has been discovered, initialised and has returned a physical probe
temperature and battery percentage.

## Consequences

The early repository has useful test and documentation structure but no REST API or MQTT service.
Hardware findings can change the later production adapter without creating migration work in
unrelated layers.

