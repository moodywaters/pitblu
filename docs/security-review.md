# v0.9.0 security and correctness review

Review dates: 8-10 September 2026. Scope: source review, automated regression tests
and clean installed-system checks against the v0.9.0rc1 implementation. This is an
engineering review, not independent penetration testing or a security certification.

## Threat model

Protect administrative access, write-only secrets, private hardware identity,
configuration integrity and honest telemetry. Clients and BLE advertisement labels
are untrusted input; the Pi's root user, reviewed installation source, package index
and bearer-token holder are trusted administrators. The service account is not root
and cannot modify its installed executable. The product deliberately supports plain
HTTP only on loopback/trusted networks; encryption requires a separately secured
deployment. An authorised administrator can select an MQTT destination by design.

## Review outcomes

| Area | Review and disposition |
| --- | --- |
| Authentication | Salted scrypt and constant-time comparison retained; malformed token lengths/characters now rejected before hashing. Hash work is off the event loop with two concurrent workers and a bounded request admission rate. Rotation invalidates the saved old hash. |
| Public surface | Only health remains unconditionally public in token mode. Candidate schema/Swagger/ReDoc routes now require authentication. Already-open SSE authenticates on admission; rotation does not revoke that stream. Documented limitation. |
| Request resources | New configurable token buckets limit authentication and authenticated mutations; at most ten immediate burst requests. Bodies capped at 16 KiB by default, including chunked input, with a five-second receive deadline. SSE default maximum eight. Global buckets avoid unbounded per-IP state and do not trust forwarded addresses. |
| Errors and secrets | Safe error envelopes, no-store/nosniff response headers, bounded correlation identifiers, write-only password fields and safe startup/validation exits. Configuration validation does not echo submitted values. Raw database/configuration/log exports are not public APIs. |
| Browser access | Explicit origins retained. Candidate exposes ETag, X-Correlation-ID and Retry-After; preflight allows correlation headers without bypassing authentication. Backend-held administrator credentials remain recommended. |
| State changes | ETag-checked transactions, parameterised SQLite values, explicit registration, serialised adapter work and ownership preserved. PATCH omission no longer clears labels. DELETE/rotation and uncertain-response retries need client confirmation/reconciliation. |
| Host commands | BlueZ recovery uses a validated registered identity and argument arrays, never shell interpolation/global reset. New read-only host diagnostics use fixed commands, timeouts, cancellation cleanup and locale-independent parsing. Raw output is not exposed. |
| Telemetry | Candidate honours the physical battery interval, preserves its actual observation time and avoids duplicate cached battery publications. Read failure invalidates its value and retries on the next snapshot. Device loss still invalidates cached readings. |
| Diagnostics | Bluetooth powered state and clock synchronisation are true/false/unknown, cached for 15 seconds. Unknown is not healthy. Readiness remains a broker-readiness check, not a guarantee of fresh probes. |
| Deployment | Dedicated user, root-owned releases, private state/configuration, lock, exclusive backups and explicit rollback retained. Additional symlink rejection for the releases directory and managed database/configuration/unit files. Same-host backup/rollback, not an automated disaster-recovery mechanism. |
| Dependencies | Local known-vulnerability query returned no advisories. Python-version/platform inventories and scans run in CI; licences/notice obligations are recorded separately. No external application source was copied or adapted. |

## Clean installed-system evidence

At exact commit `f3bc11488e72b966676c0f3a1844ea218259ab90`, clean-Pi
acceptance confirmed the dedicated nologin account and Bluetooth-group membership,
root ownership of installed code and configuration, private state and backup
permissions, and the documented systemd restrictions. The service account could
not modify installed code or root-owned configuration.

Unauthenticated ready, OpenAPI, Swagger, ReDoc, status and configuration-schema
requests returned 401 while health remained public. Authenticated access passed;
oversized input returned 413 and authentication throttling returned 429. Local
journal checks found neither the administrator token nor MQTT password. A
loopback-only broker rejected anonymous access and a least-privilege subscriber
could read but not publish. Full sanitised results are in
[clean-Pi acceptance](clean-pi-acceptance.md).

## Intentional constraints, not hidden promises

- One active thermometer, no durable temperature history or SSE replay. Queue loss
  requires REST reconciliation. No historical backfill is claimed.
- Retained broker topics can outlive deleted registrations. REST is the registry
  authority; topic cleanup remains controlled operator work.
- Service availability sequence values are reused, so clients must not apply the
  device-topic monotonic filter to service status. Last Will time is preparation time.
- All configuration changes require restart; saved configuration is not the live
  worker snapshot. There is no arbitrary OS-command or remote restart endpoint.
- Global rate limits can temporarily affect other legitimate clients. Honour 429
  Retry-After and use restrained polling. They reset with process restart.
- API body limits do not cover every socket/header/OS resource. Trusted-LAN scope
  and host/network controls remain essential. Failed authentication must not become
  a high-volume logging channel.
- Host clock reporting observes OS synchronisation status, not independent clock
  accuracy. Bluetooth powered=true does not prove successful discovery or GATT reads.
- Systemd restart supervision has a rate limit. It is not a guarantee against all
  hangs, power loss, radio interference or prolonged failure. The 16-hour soak is pending.
- Backups contain secrets; the installer executes trusted source and package builds
  as root. Do not accept arbitrary uploaded archives or backup paths from web users.

## Regression evidence and outstanding gates

Tests cover authentication/rotation, malformed tokens, request throttling/chunked
size limits, SSE admission/release, PATCH semantics, CORS/authentication, cache
headers/correlation, battery cadence/timestamps, safe host diagnostic output,
configuration conflicts, stale readings, MQTT retry and deployment-state helpers.
Run full lint, format, type, test and Linux CI checks after the final release edit.
Clean-Pi installation, operating-system permissions and physical two-probe readings
have passed. Final pull-request review remains required before v0.9.0 release
approval. The v1.0.0 four-probe suite and 16-hour soak remain pending.
