# ADR 0001: Prove the proprietary BLE path first

- Status: accepted
- Applicability: current gateway architecture

## Decision

Validate proprietary BLE discovery, initialisation, physical probe temperatures
and battery percentage on hardware before claiming support for a device model.

## Consequences

Keep focused protocol diagnostics and fixtures separate from the production API.
Hardware findings can change the adapter without adding cook semantics to the gateway.
