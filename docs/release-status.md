# v0.9.0 candidate status

The release candidate is **0.9.0rc1**, not yet the final v0.9.0 release.
The [frontend contract](frontend-integration.md) describes this candidate directly;
there is no separate older contract to reconcile.

The monorepo is moodywaters/pitblu. Gateway application identity is pitblu-core,
Python imports use pitblu_core, command names use pitblu-, environment variables
use PITBLU_, and MQTT defaults to the pitblu base topic. pitblu-web remains a
placeholder for a separately deployable frontend.

Clean installation at exact commit
`f3bc11488e72b966676c0f3a1844ea218259ab90` passed on a fresh Raspberry Pi OS
Lite 64-bit Trixie system. Native installation, security controls, REST onboarding,
physical two-probe comparison, battery cadence, SSE, MQTT, restart/reboot recovery,
backup, same-version upgrade/rollback and uninstall/restoration were verified. See
[clean-Pi acceptance](clean-pi-acceptance.md) for the dated sanitised record.

Final version preparation, pull-request CI and review remain before v0.9.0 can be
merged, tagged or published. The v1.0.0 full four-probe physical suite and minimum
16-hour soak remain separate mandatory gates.

Current source and documentation use only the new naming convention.
Git history and published historical artifacts are not rewritten by this cleanup.
