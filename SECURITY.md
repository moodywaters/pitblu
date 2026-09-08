# Security policy

## Supported deployment

The released baseline is v0.6.0. v0.9.0rc1 is an unreleased audit candidate, not
approved for unattended cooking. The gateway is for loopback or an explicitly
trusted LAN only. Do not expose its HTTP port or MQTT broker directly to the
internet. There is no built-in HTTPS, end-user account system or safety alarm.

The administrator token grants full control, including broker destination and
device/configuration changes. Keep it in a trusted backend or password manager.
Only its salted hash is stored, but MQTT passwords and protected hardware identity
are in the administrative database. Treat database backups as secrets. Root on the
Pi and the administrator credential are trusted principals, not sandboxed attackers.

## Reporting

Report suspected security problems privately to the repository maintainer through
an existing private project communication channel. Do not post credentials, private
addresses, exploit payloads containing personal data or database backups in a public
issue. Provide the affected version/revision, minimal sanitised reproduction and
expected/actual behaviour. No public disclosure deadline or response SLA is promised.

## Candidate hardening and residual limits

The candidate adds bounded request bodies, process-wide request throttling, limited
SSE connections, bounded concurrent token hashing, no-store responses, protected
documentation routes and safe startup failure text. Details and test evidence are
in the [audit report](docs/security-review.md). These are defence in depth, not
protection against a hostile public network or every denial-of-service attack.

Follow OS security updates and review dependency audit results. Do not automatically
upgrade or restart the gateway during a cook. A vulnerability scan with no findings
means no known advisories were returned for those versions at that time, not proof
that the software has no vulnerabilities.
