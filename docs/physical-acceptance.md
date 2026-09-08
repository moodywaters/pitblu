# Physical acceptance and remaining release gates

Current released baseline: v0.6.0. The full v1.0.0 physical suite and minimum
16-hour soak are **not complete**. Historical milestone passes are not a blanket
pass for this checklist. Detailed dated results are preserved in
[acceptance evidence](history/acceptance-evidence.md).

## Evidence already obtained

- Physical V202 discovery, initialisation, two probe readings matching the display,
  empty-channel detection and battery acquisition.
- API registration/control, simulated telemetry, SSE, MQTT QoS/retention/Last Will
  and stale-data transitions in targeted milestone tests.
- Targeted physical reconnection and process-recovery checks.
- Native installation under a dedicated account, token authentication, protected
  permissions, physical MQTT delivery and automatic systemd crash/reboot recovery.
- Protected backups, same-candidate upgrade/rollback, non-destructive uninstall
  and restoration, and a local check for entered credentials in the journal.

Some checks used simulation, earlier code or a same-version deployment. They are
not proof of cross-version migrations, a clean OS installation, comprehensive
security or uninterrupted long-duration operation.

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
