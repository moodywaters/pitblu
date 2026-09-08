# Native installation

These paths describe the current v0.9.0rc1 candidate.
Read [migration](rename-migration.md) before changing an existing deployment.

Target: Raspberry Pi OS Trixie, 64-bit ARM, Python 3.13, systemd and BlueZ. Docker is not used.
Migration and reboot checks passed on the existing Pi. Clean-OS installation is
still pending. Do not install during an active cook.

## Before installing

These are fresh-install instructions. For an existing managed installation, use
[upgrade and rollback](upgrade-and-rollback.md) instead; do not reinstall over it.
If migrating from an experimental setup, preserve its files as a separate fallback
and stop its process before connecting the managed service. Never run two instances
against the same thermometer or terminate arbitrary Python processes.

Install prerequisites on the Pi:

```bash
sudo apt-get update
sudo apt-get install python3-venv bluez util-linux passwd curl
```

Unpack the reviewed repository source archive. From its root, run interactively:

```bash
cd pitblu-core
sudo bash deploy/manage.sh install
```

The installer creates a system account `pitblu-core` with no login shell, adds it to the existing
`bluetooth` group, creates a new permanent virtual environment in a versioned release directory,
and installs the package there. It requires package-index access. Application source is trusted
code: review it before running the installer as root. It does not modify Mosquitto configuration.

Save the one-time administrator token in a password manager. Do not paste it into chat, command
arguments or logs. The installer refuses redirected output; SQLite stores only a salted scrypt
hash. On ordinary service startup, a missing token or disabled authentication causes failure,
never token generation into journald. Initial settings are loopback, port 8080, token authentication,
physical BLE and MQTT disabled. Configure MQTT through the API after onboarding.

The installer leaves the service stopped. Start explicitly when ready:

```bash
sudo systemctl enable --now pitblu-core
systemctl is-active pitblu-core
curl --fail http://127.0.0.1:8080/health
```

The service deliberately does not connect to unregistered devices. Register the iGrill through the
authenticated API using the [onboarding workflow](frontend-integration.md#4-discovery-registration-and-connection-workflow).
Existing databases are not imported automatically. Configure secrets through the
write-only API over loopback. Token rotation is
authenticated through the existing API. A lost initial token requires a planned local recovery,
not deleting the production database.

## Files and privileges

- `/opt/pitblu-core/releases/release-*/venv`: root-owned installed code, readable but not writable
  by the service. Virtual environments never move; `/opt/pitblu-core/current` selects one.
- `/etc/pitblu-core/config.yaml`: root-owned non-secret startup configuration, mode 0640.
- `/etc/pitblu-core/environment`: root-owned optional systemd environment file, mode 0640.
- `/var/lib/pitblu-core/state.sqlite3`: service-owned administrative state, directory 0700,
  new files masked 0077. This includes the protected MQTT password; backups are secrets too.
- `/var/backups/pitblu-core`: root-only backups, retained until explicitly managed by the operator.

`PITBLU_CONFIG_FILE` selects YAML startup configuration. `PITBLU_DATABASE_PATH` selects SQLite.
`PITBLU_MANAGED=true` enables the service authentication guard. These startup controls are not
runtime configuration values. Persisted API overrides take precedence over YAML/environment.

The unit uses a read-only system filesystem, protected home directories, no added capabilities,
no privilege escalation and a private temporary directory. It allows local D-Bus plus IPv4/IPv6
and Bluetooth socket families. Bluetooth is accessed through BlueZ, not by granting root to the
gateway. Confirm the distribution's Bluetooth group access works; do not install broad D-Bus or
polkit exceptions without diagnosing an actual permission failure.

## Operation

```bash
systemctl status pitblu-core --no-pager
sudo journalctl -u pitblu-core -n 50 --no-pager
sudo systemctl restart pitblu-core
```

Restart interrupts readings. `Restart=on-failure` restarts a failed process after five seconds;
five rapid starts in a minute trigger a limit rather than an endless failure loop. After correcting
configuration, use `sudo systemctl reset-failed pitblu-core` then start it. Stopping the service
explicitly does not restart it. Shutdown has 45 seconds to drain HTTP, BLE and MQTT before systemd
terminates remaining processes. No automatic upgrades occur.

For trusted-LAN use, explicitly configure bind `0.0.0.0` with token authentication; plain HTTP is
trusted-LAN only. Never expose the API directly to the internet. The installer makes no firewall
changes. Validate reboot startup, BLE recovery and MQTT reception before relying on the service.
