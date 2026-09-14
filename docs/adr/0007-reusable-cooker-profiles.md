# ADR 0007: reusable cooker profiles and Cook snapshots

Status: accepted

## Context

A barbecue such as a WSM or kettle is durable household equipment. Re-entering it
for every Cook makes the operator flow repetitive. Food, measurements, probe
assignments and targets remain specific to a particular Cook.

## Decision

pitblu-app stores reusable cooker profiles independently of Cooks. The no-active-
Cook screen lets the operator maintain these profiles and select one while setting
up connected probes. Selecting a profile creates a Cook-scoped cooker snapshot.

The snapshot is deliberate: renaming a saved barbecue later must not rewrite the
meaning or label of historical Cooks. Monitoring cooker temperature remains
optional. Connected physical probes are still identified by pitblu-core device ID
plus channel and are assigned to semantic cooker or food measurements.

If a Cook is already active, the operator opens that authoritative Cook directly.
After closure, the UI offers a clear route to start another Cook.

## Consequences

- WSM, kettle and other equipment details are entered once and reused.
- Food setup remains distinct and Cook-specific.
- The first operator screen is a probe-oriented quick setup rather than a generic
  administration dashboard.
- All quick-setup actions continue to use the public REST capabilities; the browser
  does not own Cook state or interpretation.
