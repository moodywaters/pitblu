# v0.9.0 candidate status

The installed gateway is **0.9.0rc1**, not the final v0.9.0 release.
The [frontend contract](frontend-integration.md) describes this candidate directly;
there is no separate older contract to reconcile.

The monorepo is moodywaters/pitblu. Gateway application identity is pitblu-core,
Python imports use pitblu_core, command names use pitblu-, environment variables
use PITBLU_, and MQTT defaults to the pitblu base topic. pitblu-web remains a
placeholder for a separately deployable frontend.

Migration, original-token authentication, physical probe/battery acquisition,
new MQTT topic delivery and reboot recovery passed on the operator's Pi on
8 September 2026. See [acceptance](physical-acceptance.md) for scope and limitations.

Clean-Pi testing is pending; follow the [rebuild checklist](rebuild-checklist.md).
The v1.0.0 full physical suite and minimum 16-hour soak remain mandatory.
Disabled predecessor files and protected backups remain locally for recovery;
cleanup is deferred. No destructive cleanup or release is authorised by this page.

Current source and documentation use only the new naming convention.
Git history and published historical artifacts are not rewritten by this cleanup.
