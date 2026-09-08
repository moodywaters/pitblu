# Physical acceptance and remaining release gates

Current candidate: v0.9.0rc1, revision f7d3879. The full v1.0.0 physical suite and
minimum 16-hour soak are **not complete**.

## Candidate evidence: 8 September 2026

- Pi Python 3.13.5: 114 tests pass, 93.79% coverage; the preceding lint, format
  and strict typing checks completed successfully in the operator's command chain.
- Migration preserved the original administrator token and registered device state.
- Physical probes 1 and 2 returned fresh 19 degrees Celsius readings; channels 3
  and 4 reported absent; battery returned 50%. Display comparison remains unconfirmed.
- MQTT authenticated as pitblu-core and delivered retained service availability
  and non-retained physical temperatures on pitblu topics, all QoS 1.
- Reboot restored service, MQTT and physical polling automatically, NRestarts=0.
  Readiness returned 200; Bluetooth power and clock synchronisation reported true.
- A verified protected backup was created after migration and reboot acceptance.

These are operator-supplied results on the existing OS, not clean-Pi installation,
four-inserted-probe acceptance, a comprehensive security audit or a 16-hour soak.
No spare card or second Pi is currently available; clean-Pi testing remains pending.

## v0.9.0 audit gates

Follow the [current audit plan](v0.9.0-plan.md): security, documentation and
provenance/licence reviews, plus clean-Pi installation. Agree a clean target with
the operator; never reimage the working Pi or replace storage without approval.

## v1.0.0 physical release checklist

Run against the final candidate, recording the exact revision and environment.
These remain final-candidate checks even where earlier milestones provide evidence.

- Discover the V202 within 20 seconds and register/connect through REST.
- Resolve expected Weber services and read all four inserted probe channels.
- Match each display within 1 degree Celsius; detect removal within 15 seconds;
  read battery; reject invalid/sentinel values.
- Mark stale data and publish service/device/probe availability correctly.
- Recover from iGrill power cycling, temporary Bluetooth failure, broker restart
  and Pi reboot without manual service restart.
- Verify REST operations, SSE, MQTT payloads/Last Will, configuration persistence,
  authentication, token rotation and secret redaction.
- Verify clean native installation, automatic startup, graceful shutdown, upgrade
  and rollback, with migration limitations stated explicitly.
- Pass supported-Python CI and complete documentation/provenance/licence reviews.
- Complete at least 16 hours of physical monitoring without manual intervention;
  record sample freshness, MQTT receipt, telemetry gaps, interruptions and automatic
  recovery. Review every gap; merely leaving the process running is not a pass.

## Safe test procedure and evidence

Arrange disruptive checks outside an active cook. Close competing thermometer apps
and run only one gateway against the physical device. Keep independent temperature
checks. Use small related batches of Pi commands and review results before proceeding.
Stop at hardware decisions requiring operator input.

Record dates, revision, OS/Python/BlueZ versions, steps, expected and actual outcomes,
manual display comparisons, timing and recovery details. Omit private addresses,
credentials and raw databases. Distinguish simulation from physical evidence.
A failed or unrun check stays failed or pending; a healthy endpoint alone is not a pass.
