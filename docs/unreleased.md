# Unreleased changes

This page describes changes on the v0.9.0 audit branch, not a released or installed
runtime. The package version remains v0.6.0 during development; version alone cannot
identify an unreleased checkout. Record its Git revision when testing. Current
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

## Validation boundary

These are local software fixes. They do not complete the wider security/licence
audit, supported-Python CI, clean-Pi acceptance or minimum 16-hour physical soak.
No Pi upgrade is requested by this page. When released, fold these semantics into
the current guides and remove the superseded caveats and this temporary page.
