# Documentation index

## Version and scope

Current user and integration guides describe **released v0.6.0**. The v0.9.0 audit
is in development and v1.0.0 physical acceptance, including the minimum 16-hour soak,
is pending. Newer documentation on a development branch does not imply a newer
runtime has been released or installed.

## For cooks

- [Plain-English overview](bbq-overview.md)
- [Quick start](bbq-quick-start.md)

## Setup and operation

- [Installation](installation.md)
- [Backup, upgrade, rollback and uninstall](upgrade-and-rollback.md)
- [Troubleshooting](troubleshooting.md)

## Frontend builders and contributors

- [Complete frontend/AI handoff](frontend-integration.md): all endpoints, settings,
  SSE/MQTT schemas, examples, workflows and implementation limitations.
- [REST](api.md), [configuration](configuration.md), [MQTT](mqtt.md)
- [Architecture](architecture.md), [Bluetooth protocol](bluetooth.md)
- [Development](development.md), [contributing](../CONTRIBUTING.md)

## Release assurance and historical records

- [Current acceptance checklist](physical-acceptance.md)
- [Active v0.9.0 audit plan](v0.9.0-plan.md), not completed functionality
- [Changelog](../CHANGELOG.md), dated release history
- [Historical acceptance evidence](history/acceptance-evidence.md), not a runbook
- [Provenance](provenance.md), [third-party notices](../THIRD_PARTY_NOTICES.md), [licence](../LICENSE)
- Decisions: [hardware-first](adr/0001-incremental-hardware-first.md),
  [adapter boundary](adr/0002-device-adapter-boundary.md),
  [REST/configuration/authentication](adr/0003-rest-configuration-and-auth.md)
- [Target specification](../pitboss-admin-project-plan.md) and
  [AI continuation record](../pitboss-admin-codex-prompt.md): development context,
  not end-user instructions. Unimplemented requirements remain targets.

## Maintenance policy

Maintain one current installation path and integration contract. Remove superseded
plans and obsolete command sequences from active documentation; Git history retains
them. Preserve changelogs, licence/provenance, significant decisions and useful dated
test evidence with explicit historical labels.

Update affected guides alongside code changes. Verify relative links and examples,
state the release baseline, and distinguish implemented functionality, limitations
and pending acceptance. Never rewrite old evidence to imply newer code was tested.
Keep credentials and private deployment details out of examples. Beginner guides
must stay accurate without requiring readers to understand the technical reference.
