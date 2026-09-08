# Moving an existing installation to pitblu-core

Status: migration procedure planning, not physically accepted. Do not run the new
installer as an upgrade over a deployment using a different application identity.
The running installation has not been changed by the source/repository rename.

## What changes

New installations use `/opt/pitblu-core`, `/etc/pitblu-core`,
`/var/lib/pitblu-core` and `/var/backups/pitblu-core`. The service and Linux account
are `pitblu-core`; commands are `pitblu-api`, `pitblu-state`, `pitblu-ble-proof`
and `pitblu-v202-check`. Python imports use `pitblu_core`, environment variables
start with `PITBLU_`, and the default MQTT base topic is `pitblu`.

REST resource paths, stable device identifiers, SQLite schema and telemetry JSON
remain unchanged. Existing saved MQTT topics and credentials are configuration,
not defaults: they will not automatically change when copied to the new deployment.

## Controlled migration checklist

1. Schedule downtime outside a cook. Identify the actual running unit, application,
   configuration and database paths through read-only inspection. Do not guess them
   from renamed historical documentation.
2. Make and verify a protected SQLite snapshot and backup of configuration, unit
   and release target. Keep these outside source control. Preserve the original
   deployment until the replacement passes acceptance.
3. Stop the identified service and confirm its process and listener have stopped.
   Never run two gateway instances against the same thermometer or database.
4. Install the new candidate under its new account and paths. Recreate the virtual
   environment rather than moving it: executable launchers contain absolute paths.
5. Restore administrative state using a validated SQLite snapshot, preserving token
   hashes, registrations and desired state. Set ownership to the new service account
   and retain the documented restrictive permissions.
6. Translate environment variable names and path values in protected configuration.
   Review persisted overrides too. Provision the new MQTT identity and topic ACL
   explicitly, verifying authentication without printing its password. Coordinate
   topic changes with consumers; old retained availability must not imply a live
   publisher after cutover.
7. Start only the replacement service. Verify the original administrator token,
   physical probe/battery readings, MQTT delivery, reboot recovery and backup.
8. If verification fails, stop the replacement before restoring the protected
   original deployment. Remove obsolete on-device files/accounts only after
   successful acceptance and explicit agreement about retained recovery backups.

Exact commands will be prepared from the operator's actual deployment inventory.
Repository history, existing release archives and recovery backups are historical
records; this rename does not rewrite or destroy them.
