# Changelog

This file is the canonical human-readable version history. Git tags and GitHub
releases are authoritative for published revisions.

## [0.9.0] - 2026-09-10

- Added the native Raspberry Pi gateway with REST administration, SSE events and
  optional MQTT telemetry for Weber iGrill V202 thermometers.
- Added explicit device registration, stable public identifiers, physical and
  simulated adapters, four logical probe channels and supervised recovery.
- Added bearer authentication and rotation, request and stream limits, typed
  versioned configuration, write-only secrets and safe diagnostics.
- Added hardened systemd deployment, protected backup, upgrade, rollback and
  non-destructive uninstall workflows.
- Added the complete frontend integration contract, operator documentation,
  dependency inventories, licence/provenance records and Python 3.11-3.13 CI.
- Passed clean-Pi acceptance on Raspberry Pi OS Lite 64-bit Trixie at commit
  `f3bc11488e72b966676c0f3a1844ea218259ab90`: 114 tests, 93.79% coverage,
  native installation/security checks, two-probe display comparison, battery,
  SSE, MQTT, restart/reboot recovery and maintenance workflows.

The accepted runtime was labelled `0.9.0rc1`. The final `0.9.0` preparation changes
release metadata and documentation only; it does not alter gateway runtime logic.
The complete four-probe physical suite and minimum 16-hour soak remain v1.0.0 gates.
