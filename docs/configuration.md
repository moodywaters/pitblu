# Configuration

The [frontend integration guide](frontend-integration.md) lists every setting and
explains configuration-editor workflows and saved-versus-running behaviour.

The v0.9.0rc1 candidate exposes typed application settings through REST. Precedence is:

1. package default;
2. optional YAML startup file;
3. `PITBLU_` environment values using `__` between path components;
4. transactional persisted override.

For example, `PITBLU_BLUETOOTH__SCAN_DURATION=7` sets `bluetooth.scan_duration`. YAML and
environment input use safe YAML scalar parsing. Unknown settings and invalid combinations stop
configuration loading.

For native deployment, `PITBLU_CONFIG_FILE` selects the YAML file and must name an existing file.
`PITBLU_DATABASE_PATH` and `PITBLU_MANAGED` are also deployment controls, excluded from normal
setting parsing. Managed mode requires token authentication and a previously bootstrapped hash;
it never generates an initial token in service logs. See [installation](installation.md).

## Setting families

- `server`: bind address, port and explicit CORS origins;
- `auth`: disabled or bearer-token mode;
- `security`: authentication/mutation admission, body size and simultaneous SSE limits;
- `bluetooth`: scan, connection, initialisation and read timings;
- `polling`: probe, battery, stale, degraded, reconnect, heartbeat and stable timings;
- `mqtt`: enabled state, broker host and port, TLS, username, base topic and fixed QoS 1;
- `simulation`: disabled-by-default mode and one to four probes.

Each setting response contains its effective value, source, type, description, default, minimum,
maximum, allowed values, editability, sensitivity and restart requirement. Secret values are never
part of this mapping.

The current implementation applies persisted changes on the next process start, so every setting
is reported with `restartRequired: true`.

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

`PITBLU_DATABASE_PATH` is a deployment-level startup override rather than an application setting.
The development default is `pitblu-core.sqlite3` in the working directory. The native
installer sets the production path under `/var/lib/pitblu-core/` with restricted permissions.

Physical battery acquisition follows its interval and preserves cached observation timestamps.
Saved settings can differ from workers' startup values until restart. See the
frontend guide for metadata limitations and saved-versus-running behaviour.
