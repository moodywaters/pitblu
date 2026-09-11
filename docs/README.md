# Documentation index

## Version and scope

Current guides describe v0.9.0 beta. Clean-Pi acceptance passed at the exact runtime
revision recorded in the acceptance document. The v1.0.0 physical suite and minimum
16-hour soak are separate pending gates. `CHANGELOG.md` is the canonical human-
readable version history; Git tags and releases are authoritative once published.

## For cooks

- [Plain-English overview](bbq-overview.md)
- [Quick start](bbq-quick-start.md)

## Setup and operation

- [Guided terminal tools](terminal-tools.md): normal install, configuration and support workflow
- [Installation](installation.md)
- [Fresh-OS rebuild checklist](rebuild-checklist.md)
- [Backup, upgrade, rollback and uninstall](upgrade-and-rollback.md)
- [Troubleshooting](troubleshooting.md)

## Frontend builders and contributors

- [Complete frontend/AI handoff](frontend-integration.md): all endpoints, settings,
  SSE/MQTT schemas, examples, workflows and implementation limitations.
- [REST](api.md), [configuration](configuration.md), [MQTT](mqtt.md)
- [Architecture](architecture.md), [Bluetooth protocol](bluetooth.md)
- [Development](development.md), [contributing](../CONTRIBUTING.md)

## Release assurance

- [Current acceptance checklist](physical-acceptance.md)
- [Security policy](../SECURITY.md) and [candidate security review](security-review.md)
- [Dependency audit](dependency-audit.md) and [clean-Pi procedure](clean-pi-acceptance.md)
- [Active v0.9.0 audit plan](v0.9.0-plan.md), not completed functionality
- [Candidate status](release-status.md), validation and publication boundaries
- [Changelog](../CHANGELOG.md), v0.9.0 onward
- [Provenance](provenance.md), [third-party notices](../THIRD_PARTY_NOTICES.md), [licence](../LICENSE)
- Decisions: [hardware-first](adr/0001-incremental-hardware-first.md),
  [adapter boundary](adr/0002-device-adapter-boundary.md),
  [REST/configuration/authentication](adr/0003-rest-configuration-and-auth.md) and
  [guided terminal boundaries](adr/0004-guided-terminal-tools.md)
- [Target specification](../pitblu-core-project-plan.md) and
  [AI continuation record](../pitblu-core-codex-prompt.md): development context,
  not end-user instructions. Unimplemented requirements remain targets.

## Maintenance policy

Maintain one current installation path and integration contract. Remove superseded
plans and obsolete command sequences from active documentation; Git history retains
them. Active documentation begins at v0.9.0. Preserve relevant licence/provenance
and architectural rationale without obsolete milestone instructions.

Update affected guides alongside code changes. Verify relative links and examples,
state the release baseline, and distinguish implemented functionality, limitations
and pending acceptance. Never rewrite old evidence to imply newer code was tested.
Keep credentials and private deployment details out of examples. Beginner guides
must stay accurate without requiring readers to understand the technical reference.
