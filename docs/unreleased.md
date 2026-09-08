# Unreleased changes

This page describes changes on the v0.9.0 audit branch, not a released or installed
runtime. The audit candidate reports v0.9.0rc1. Record its Git revision when testing. Current
release instructions and the frontend guide remain based on the v0.6.0 release tag.

## Partial device updates

`PATCH /api/v1/devices/{deviceId}` now preserves friendlyName when the field is
omitted. Explicit `{"friendlyName":null}` still clears it; a supplied string renames
the device. An empty patch leaves a known device unchanged and returns it; an
unknown device still returns 404. Updating only automaticReconnection or discoveryId
no longer clears the name. No database migration is required.

Regression coverage includes empty updates, recovery-preference-only updates,
identity-only updates, explicit clearing, renaming and missing devices.

## Browser configuration access

When CORS origins are explicitly configured, allowed browsers can now read ETag
and X-Correlation-ID response headers and send X-Correlation-ID in requests.
Authorization, Content-Type and If-Match remain allowed. Origin restrictions and
bearer authentication are unchanged. A successful preflight is not permission to
perform an unauthenticated API operation.

Regression tests cover preflight, readable headers, a version-checked configuration
update, correlation propagation, rejected origins and unauthenticated rejection.
This does not make browser-held administrator credentials advisable; a separate
web backend remains the recommended integration architecture.

## Additional candidate behaviour

- Physical battery acquisition now follows polling.battery_interval (300 seconds
  by default) on the first eligible probe cycle. Actual cadence includes work and
  scheduling time. Cached battery readings retain their own observation time;
  MQTT/SSE do not republish them as new battery observations every probe cycle.
  Failed battery reads invalidate the value and retry next cycle. Reconnection
  forces a new read. Device staleness/disconnection also invalidates the cache.
- Status/diagnostics add `host`: `bluetoothPowered` and `clockSynchronized`, each
  true, false or null (unknown). Read-only host checks are cached for 15 seconds.
  `/bluetooth.available` is powered state for physical mode, or true for simulation.
  It is not proof of successful GATT reads. Missing/failed OS tools report unknown.
- Documentation routes `/docs`, `/redoc` and `/openapi.json` now follow token
  authentication. A browser needs a trusted backend relay supplying the header for
  both HTML and schema requests; an ordinary address-bar visit does not add a token.
- All responses use no-store and nosniff headers. Invalid correlation identifiers
  are replaced, not reflected; accepted identifiers use 1..64 letters, digits,
  dots, underscores or hyphens. Startup configuration failures suppress raw values.
- `security.auth_requests_per_minute`: default 300, range 10..3600, process-wide
  authentication admission. `security.mutations_per_minute`: default 30, range
  1..300, process-wide POST/PATCH/PUT/DELETE admission after authentication.
  Both use token buckets with burst capacity min(rate,10), not fixed calendar windows.
  Rejected requests return 429 `rate_limited` and Retry-After seconds. Poll modestly
  and retry only when safe; the limits cover all clients and reset on process restart.
- `security.maximum_body_bytes`: default 16384, range 8192..65536; mutation bodies,
  including chunked bodies, return 413 `request_too_large` above this limit. A body
  taking more than five seconds to receive returns 408 `request_timeout`.
- `security.maximum_sse_clients`: default 8, range 1..32. Extra streams receive 429;
  capacity is released when a response ends or is cancelled. Token hashing has two
  concurrent workers and malformed generated-token formats are rejected cheaply.
- New security settings have the same configuration metadata/ETag/restart rules as
  existing settings. Retry-After is exposed to permitted browser origins too.
- Deployment rejects symlinked managed state/configuration/unit files and releases
  directories. No automatic update, pairing reset or data deletion is introduced.

## Validation boundary

These are local software fixes. They do not complete the wider security/licence
audit, supported-Python CI, clean-Pi acceptance or minimum 16-hour physical soak.
No Pi upgrade is requested by this page. When released, fold these semantics into
the current guides and remove the superseded caveats and this temporary page.
