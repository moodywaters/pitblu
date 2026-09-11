# ADR 0004: Keep guided terminal tools outside the service process

- Status: accepted
- Applicability: v1.0 terminal installation, configuration and support workflows

## Decision

Provide two small terminal applications:

- `pitblu-core-install` performs host checks and guides installation or upgrade by delegating
  privileged deployment work to `deploy/manage.sh`.
- `pitblu-core-config` configures and diagnoses an installed service through its loopback REST API.

Both applications remain unprivileged. They invoke only fixed, reviewable `sudo` command arrays;
they never build shell command strings. The configuration tool accepts administrator credentials
only through a hidden terminal prompt and never through command-line arguments. It uses the
service's validation, ETag and write-only secret endpoints instead of opening the database or
configuration files directly.

The source checkout contains a bootstrap launcher because the package is not available before the
first installation. The deployment script installs stable launchers in `/usr/local/bin`. Uninstall
removes the configuration launcher because no service remains to configure, but retains the
installer launcher as a recovery route.

`pitblu-core-config check` is the canonical support command. Results always carry the words PASS,
WARN or FAIL; colour is an optional TTY enhancement and is disabled when `NO_COLOR` is present.

The supported host policy is:

- PASS for Raspberry Pi OS or Debian 13 on aarch64 with supported Python;
- WARN for other technically plausible Debian-like Linux systems;
- FAIL for unsupported operating systems, Python versions or architectures.

Dependency installation is an explicit opt-in prompt whose default is No. Structured JSON and
non-interactive mutation interfaces are intentionally deferred.

## Security boundaries

The first-install administrator token may be displayed once by the existing state bootstrap tool,
and only on a TTY. The installer does not capture, repeat, log or persist the cleartext token and
clearly tells the operator to save it securely. Configuration remains local-only for v1.0, even if
the service has been deliberately configured to listen elsewhere.

Terminal text originating outside the tools is stripped of control characters before display.
Secrets and bearer tokens are excluded from errors, process arguments and diagnostic output.

## Consequences

The service runtime and its v0.9 security model do not gain an additional privileged or local-file
configuration path. Installation remains recoverable through the proven deployment script, while
normal operators receive a guided interface. Some end-to-end behaviours still require Raspberry
Pi, BlueZ and physical iGrill validation before the v1.0 gates can pass.
