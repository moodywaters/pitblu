# Configuration

Version 0.3.0 exposes every planned application setting through REST. Precedence is:

1. package default;
2. optional YAML startup file;
3. `PITBOSS_` environment values using `__` between path components;
4. transactional persisted override.

For example, `PITBOSS_BLUETOOTH__SCAN_DURATION=7` sets `bluetooth.scan_duration`. YAML and
environment input use safe YAML scalar parsing. Unknown settings and invalid combinations stop
configuration loading.

## Setting families

- `server`: bind address, port and explicit CORS origins;
- `auth`: disabled or bearer-token mode;
- `bluetooth`: scan, connection, initialisation and read timings;
- `polling`: probe, battery, stale, degraded, reconnect, heartbeat and stable timings;
- `mqtt`: enabled state, broker host and port, TLS, username, base topic and fixed QoS 1;
- `simulation`: disabled-by-default mode and one to four probes.

Each setting response contains its effective value, source, type, description, default, minimum,
maximum, allowed values, editability, sensitivity and restart requirement. Secret values are never
part of this mapping.

`PATCH /api/v1/config` requires the current quoted ETag in `If-Match`. The full candidate is
validated before persisted overrides are replaced in one SQLite transaction. A stale version
returns HTTP 409 and changes nothing. `POST /api/v1/config/validate` performs the same whole-model
validation without persisting.

`mqtt.password` is currently the only allowed secret name. Its responses contain only name,
configured state and change time. The value is write-only. Administrator tokens are separate:
only a salted scrypt hash is stored, and rotation returns a replacement plaintext token once.

Authentication may be disabled only with the loopback bind. Before changing `auth.mode` to `token`,
rotate an administrator token while still on the safe loopback connection. A configuration update
cannot enable token mode without a stored token hash.

`PITBOSS_DATABASE_PATH` is a deployment-level startup override rather than an application setting.
The development default is `pitboss-admin.sqlite3` in the working directory. The v0.6.0 native
installer will set the production path under `/var/lib/pitboss-admin/` with restricted permissions.
