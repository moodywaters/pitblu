# Backup, upgrade, rollback and uninstall

v0.6.0 procedures passed same-candidate lifecycle testing on the Pi. Never upgrade during a cook.
All operations use a deployment lock and fixed production roots. The home-directory test installation
is not modified. Old releases and backups are retained; there is no automatic garbage collection.

## Backup

```bash
sudo bash /opt/pitboss-admin/current/manage.sh backup
```

This creates a new root-only directory under `/var/backups/pitboss-admin`, prints its path and
stores a consistent SQLite snapshot, configuration/environment files, unit and selected release
path. It never overwrites a backup. Avoid configuration edits during the snapshot/copy interval.
Backups contain secrets. Copy them only to protected storage, never GitHub or a support transcript.
The selected application release must remain present for rollback; also retain its source archive.

## Upgrade

Unpack the new source release into a separate directory. Then run from that directory:

```bash
sudo bash deploy/manage.sh upgrade
```

The installer builds a new virtual environment before stopping the running service. Once stopped,
it backs up state/configuration and selects the new release, preserving the old directory. It
validates managed authentication and starts the service. No credential or registration is replaced.
A command failure after backup leaves the service stopped and reports the backup path, rather than
restarting an older binary against possibly migrated state. If startup fails asynchronously, inspect
the journal and perform rollback explicitly. Verify health, authenticated API, device freshness and
MQTT reception after every upgrade; a successful systemctl start alone is not acceptance.

## Rollback

Use the exact backup directory printed before that upgrade:

```bash
sudo bash /opt/pitboss-admin/current/manage.sh rollback /var/backups/pitboss-admin/backup-REPLACE_ME
```

Rollback stops the service, creates a safety backup of the current state, validates the selected
backup and restores its database, two startup files, systemd unit and release selection. It starts
the previous service. Later configuration/registration/secret changes are replaced by the older
snapshot but remain recoverable from the safety backup. Do not rename or remove release directories
referenced by backups. Verify authentication and telemetry again; the older token hash is restored.
Additional operator-created config files are left untouched; only the two managed startup files
are restored. To restore onto a replacement Pi, recreate the same release paths and service account
under controlled administration; this is same-host rollback, not an automated disaster recovery tool.

## Uninstall without data deletion

```bash
sudo bash /opt/pitboss-admin/current/manage.sh uninstall
```

This disables/stops the service and moves its unit to the application directory for recovery.
The account, code, configuration, state and backups remain. No data purge is provided. To restore
the service, install the saved unit back to `/etc/systemd/system/pitboss-admin.service`, reload
systemd and enable/start explicitly. If installation fails part-way, inspect retained paths before
retrying; do not recursively delete production directories.
