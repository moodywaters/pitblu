# Clean-Pi acceptance: v0.9.0 candidate

Status: pending operator-provided clean target. Do not erase or reimage the working
installation. Use an explicitly agreed spare microSD card or separate Pi with a
fresh supported OS. Existing-Pi upgrade/rollback tests are not clean-install evidence.

## Prepare and preserve

1. Agree the spare target/card, candidate Git revision and source archive before
   running commands. Keep the working card and protected backups untouched.
2. Install fresh 64-bit Raspberry Pi OS Trixie on the spare target with the operator's
   normal secure setup. Confirm Pi model, OS, Python and BlueZ versions. Do not
   record private addresses or credentials in the public evidence.
3. On a separate Pi, stop the original gateway explicitly before testing the same
   iGrill, outside a cook. On a spare card, shut down the Pi properly before swapping.
   Never run competing gateway/proof processes against the thermometer.
4. Confirm no pitblu-core account, application/configuration/state roots or unit
   already exist. Unexpected paths pause the test, not authorise deleting them.

## Candidate software checks

Unpack the reviewed candidate archive into a new source directory on the clean Pi.
From that directory, use the [development checks](development.md), including tests,
typing, formatting, linting and installer shell syntax. Record results and revision.
Do not put the virtual environment or database in the source release archive.

## Installation and functional acceptance

Follow [native installation](installation.md) from the candidate source directory:

- Prerequisites install; service account and bluetooth group setup succeed.
- Installation displays the initial token once in an interactive terminal and
  leaves the service stopped. Save it privately; report only successful bootstrap.
- Explicit enable/start succeeds; reboot enables automatic startup.
- Health is public; ready, status, schema and documentation reject missing tokens.
- Correct token grants access; request-size/rate errors are safe and contain no secret.
- Configuration/state ownership and permissions match the native guide; the service
  cannot modify its executable or root-owned configuration.
- Host diagnostics report useful Bluetooth/clock state or explain unknown without
  leaking command output. Confirm actual clock synchronisation locally.
- Register/connect the physical iGrill through REST using fresh discovery results.
  Compare both available physical probes with the display, check absent sockets
  and battery. Confirm battery observation time stays unchanged between battery
  polls while probe readings advance, then advances after the configured interval.
- Connect a separate MQTT subscriber using least-privilege credentials; verify
  source, session, retained service state, non-retained temperatures and battery timing.
- If testing MQTT, prepare a test broker explicitly or use an operator-approved
  existing broker without overwriting its configuration. MQTT-disabled API operation
  must also work; disabled MQTT alone does not satisfy the MQTT acceptance item.
- Exercise SSE and close it cleanly; verify explicit disconnect/reconnect, service
  restart and fresh readings. Do not infer success solely from /health or /ready.
- Back up, perform a controlled candidate upgrade/rollback cycle and verify original
  credentials, device identity/settings and physical readings survive. State whether
  this was same-version or cross-version testing.
- Check the journal locally for the entered token/password without printing either.
- Test non-destructive uninstall preserves data and documented restoration works.

Use small related command batches and review each result before the next destructive
or hardware-sensitive action. A test failure pauses release; preserve evidence and
diagnose it instead of continuing through a broken installation.

## Required record and completion

Record candidate revision, fresh-target provenance, OS/Python/BlueZ versions, commands
or procedure references, sanitised results, probe/display comparison and any manual
intervention. Append a dated record to historical evidence only after actual results.
Keep a clear pass/fail/not-run result for every item. Mark v0.9.0 complete only after
this gate and final software/CI/audit checks pass. The 16-hour physical soak and full
four-inserted-probe suite remain v1.0.0 gates, not claimed by this procedure.

Return to the original installation only through an agreed shutdown/card-swap or
service-start plan. Retain test evidence and protected backups; no automatic cleanup.
