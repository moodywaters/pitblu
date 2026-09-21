# Changelog

## 0.5.0 - 2026-09-21

### Cook Domain Foundation

- Confirmed physical probe identity as the `coreDeviceId` and `probeChannel` pair.
- Preserved Measurements as semantic Cook concepts independent of physical probes.
- Preserved explicit, time-bounded Probe Assignments and unassigned telemetry gaps.
- Corrected delayed telemetry interpretation to use the assignment covering `observedAt`, preventing reassignment from rewriting historical meaning.
- Allowed a Measurement's current Cooker/Food context to change without changing its Probe Assignment.
- Made Cook close end every remaining active assignment at the exact Cook close timestamp.
- Added regression coverage for assignment history, probe replacement, reassignment, temporal gaps, alerts, events and Cook close behavior.

No Cook UI redesign, Cooker configuration, zones, images, or Live Cook assignment controls are included in this release.
