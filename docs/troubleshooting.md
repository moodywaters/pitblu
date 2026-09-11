# Troubleshooting the current managed service

Current release: v0.9.0. For plain-English help, start with the
[cook's quick start](bbq-quick-start.md). These checks concern the installed service,
not an old milestone proof process.

## Start with the supported check

On the Pi, run:

```bash
pitblu-core-config check
```

It asks for the administrator token without echo and reports every normal support layer without
showing secrets or Bluetooth addresses. If the port changed, use
`pitblu-core-config --port PORT check`. Low-level service status and logs belong to safe escalation,
after this report.

## Common symptoms

| Symptom | Check |
| --- | --- |
| Connection refused | Correct host/port and service state. Loopback means this computer, not a remote Pi. |
| HTTP 401 | Use the saved administrator token. It is not the MQTT password. A rotated token replaces the old one. |
| Service healthy but probes empty | No snapshot yet. Check registration, desired connection state, device power and discovery. |
| Backoff or stale readings | Check iGrill power/battery, probe insertion, Bluetooth range and competing phone apps. Allow recovery time. |
| Solid iGrill Bluetooth light but no readings | A radio connection is not proof of completed initialisation or successful GATT reads. Inspect safe failureStage diagnostics. |
| MQTT degraded / readiness 503 | Check broker availability and credentials. Saved-password confirmation proves storage, not authentication. |
| Settings saved but behaviour unchanged | Settings and MQTT secret changes require service restart; no REST restart action exists. |
| Readings marked simulated | Check simulation.enabled and restart only when safe. Do not use test readings for a cook. |
| Scan result no longer available | Rescan and explicitly select a fresh discoveryId. Do not guess a Bluetooth address or automatically rebind hardware. |
| SSE reconnect leaves a gap | Refetch current REST state. There is no historical replay. |

## Safe escalation

Do not start `pitblu-ble-proof`, `pitblu-v202-check` or another API process against
the same thermometer while the managed service owns it. Do not reset Bluetooth,
remove pairing, delete state or repeatedly restart the service as a first response.
Such actions can interrupt a cook and erase useful evidence.

Inspect recent service logs locally if needed:

```bash
systemctl status pitblu-core --no-pager
sudo journalctl -u pitblu-core -n 50 --no-pager
```

Review logs before sharing. Never send tokens, MQTT passwords, database backups,
private addresses or unreviewed environment/configuration files. Report version,
safe errorCode/failureStage, time of failure, physical versus simulated source and
the iGrill display comparison. Do not assert a root cause from a generic failure code.

If the token is lost, arrange controlled local recovery; do not delete the database.
If the service has reached its restart limit, diagnose and correct the cause before
resetting it. Maintenance commands and rollback behaviour are in
[installation](installation.md) and [upgrade/rollback](upgrade-and-rollback.md).
Never perform disruptive recovery or upgrade during a cook without operator approval.
