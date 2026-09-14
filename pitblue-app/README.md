# pitblue-app

`pitblue-app` is the cook application behind the user-facing **Pitblu** product.
It owns cooks, semantic measurements, time-bound probe assignments, temperature
history, targets, alerts, events, sharing and the operator/display/follower clients.
`pitblu-core` remains the authoritative thermometer gateway.

The application is platform-neutral. It has no dependency on Raspberry Pi hardware,
ARM, GPIO, BlueZ, BLE or a particular filesystem layout. Raspberry Pi is one
supported deployment target; the application may run on Linux, Windows, macOS or
another Python host provided it can reach pitblu-core over REST and SSE.

## Run locally

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PITBLU_CORE_URL=http://127.0.0.1:8080 \
PITBLU_CORE_TOKEN=replace-with-core-token \
PITBLUE_APP_OPERATOR_TOKEN=replace-with-a-random-32-character-token \
PITBLUE_APP_DISPLAY_TOKEN=replace-with-a-different-random-32-character-token \
.venv/bin/pitblue-app
```

On Windows, use `.venv\Scripts\python.exe` and set environment variables in the
shell. The app listens on port 8081 by default. Open `/` for the operator client,
`/display` for the permanent wallboard, `/docs` for OpenAPI, and a generated
`/follow/{token}` path for a mobile follower.

Configuration variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PITBLUE_APP_DATABASE` | `pitblue-app.sqlite3` | Application SQLite database |
| `PITBLUE_APP_BIND` | `0.0.0.0` | LAN listener address |
| `PITBLUE_APP_PORT` | `8081` | Application port |
| `PITBLUE_APP_OPERATOR_TOKEN` | required | Full API and operator-client bearer token (at least 32 characters) |
| `PITBLUE_APP_DISPLAY_TOKEN` | required | Read-only permanent-display token (at least 32 characters) |
| `PITBLUE_APP_INTEGRATION_TOKEN` | unset | Optional bearer token limited to events and lifecycle actions |
| `PITBLU_CORE_URL` | `http://127.0.0.1:8080` | Server-side core URL |
| `PITBLU_CORE_TOKEN` | unset | Core bearer token; never sent to clients |

All configured application tokens must be distinct. The operator and display
clients ask for their respective token and retain it only for the browser tab
session. Non-browser clients send `Authorization: Bearer <token>`. Follower links
remain separate, revocable,
cook-scoped capabilities and do not accept an application bearer token as a way to
broaden their access.

## Optional Linux/systemd deployment example

The files under `deploy/` are one optional Linux service recipe, suitable for a
Raspberry Pi or another systemd host. They are not application architecture or
mandatory paths. Install the reviewed package into `/opt/pitblue-app/venv`, create an unprivileged
`pitblue-app` system user and its private `/var/lib/pitblue-app` directory, then copy
`deploy/pitblue-app.service` to `/etc/systemd/system/`. Copy
`deploy/environment.example` to `/etc/pitblue-app/environment`, set mode `0640`, and
add the core token locally. Never commit or place that token in a command argument.

After reviewing paths and permissions:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pitblue-app
curl --fail http://127.0.0.1:8081/health
```

The service runs without root, has a read-only system filesystem, and can write only
its application-state directory. Put a firewall boundary around port 8081 and expose
it only to the trusted LAN. Do not expose Pitblu or follower URLs to the internet.

Back up `/var/lib/pitblue-app/state.sqlite3` while the service is stopped. For an
upgrade, retain that backup and the previous wheel, install the reviewed release,
start the service, and verify `/health`, `/ready`, an existing completed cook, and
core connectivity. Roll back by stopping the service, restoring the prior wheel and
compatible database backup, then starting and verifying again.

## API and data model

All meaningful operations use `/api/v1`. Generated OpenAPI documents the exact
routes and schemas. The application SSE stream is `/api/v1/events`; reconnecting
clients first fetch authoritative REST state. `Idempotency-Key` makes Add Event
retries safe.

| Capability | Main routes |
| --- | --- |
| System | `GET /health`, `/ready`, `/api/v1/system` |
| Cooks | `GET/POST /api/v1/cooks`, `GET/PATCH /api/v1/cooks/{id}` |
| Lifecycle | Cook-scoped `/start`, `/finish-cooking`, `/start-rest`, `/serve`, `/close` |
| Structure | Cook-scoped `/cookers`, `/food-items`, `/measurements`, `/assignments` |
| Telemetry | `GET /api/v1/cooks/{id}/telemetry?start=&end=&maxPoints=` |
| Events | Cook-scoped `GET/POST /events`; writes accept `Idempotency-Key` |
| Alerts | `GET /api/v1/alerts`; detail and acknowledgement routes |
| Sharing | Cook-scoped `GET/POST /shares`; revoke and token-scoped follower state, telemetry, events and SSE |

Application SSE frames contain `eventId`, `type`, `occurredAt`, and structured
`data`. Events cover cook lifecycle changes, measurements, assignments, cook events,
and alert trigger, acknowledgement, and resolution. The stream has no replay;
reconnecting clients fetch REST state before resuming.

Physical sources are `(coreDeviceId, probeChannel)` pairs, not global channel
numbers. Assignments have start/end times, and each reading stores the assignment
and semantic measurement that were active at observation time. Core `observedAt`
drives chronology; `receivedAt` is diagnostic. Unavailable readings remain explicit
gaps and are never presented as live values.

Food targets default to a 3°C approaching margin. Food and cooker conditions are
evaluated by the backend and exposed as structured, stateful alerts. Acknowledging
an alert does not resolve its physical condition.

Follower tokens contain 256 bits of randomness, are stored only as SHA-256 hashes,
are read-only and scoped to one cook. They can be revoked and expire automatically
when the cook closes. Follower telemetry omits device, channel, assignment and
diagnostic receive metadata. Its SSE stream filters application events to the shared
cook. Milestone 1 is for trusted LAN deployment, not public sharing.

Starting a Cook ensures one backend-managed default follower share for the Live
Display QR code. The display token may read that default capability but cannot mint,
regenerate or revoke shares. If the invariant is missing at startup or read time,
the backend repairs it. The default token is reconstructed from a stored random
nonce and a server-side signature; only its SHA-256 hash is stored for lookup.
Operator scope retains the explicit manual share, revocation and default-share
regeneration APIs.

## Development and persistence

Run `python -m pytest` from this directory. SQLite uses ordered, versioned migrations
through `PRAGMA user_version`; startup upgrades older supported schemas atomically
and refuses a database from a newer unsupported application version. Back up the
database before upgrades. Restore by stopping the service and replacing the database
with a verified compatible backup. The API process must remain running for recording
and alerts; no browser is required.

The official frontend lives in `frontend/` and uses React, TypeScript and Vite. For
frontend development, run FastAPI on port 8081 and then:

```bash
cd frontend
npm install
npm run dev
```

Run `npm test` for frontend tests. `npm run build` type-checks the frontend and
writes its production bundle into `src/pitblue_app/static/`; rebuild before creating
a Python wheel. FastAPI serves that bundle in production, so deployed hosts need no
Node runtime or separate JavaScript server. The generated service worker caches the
application shell, not authenticated API responses or Cook data.

All state and interpretation remain in the typed backend. React owns presentation,
temporary form state and live invalidation only; TypeScript models API payloads and
application SSE envelopes without reimplementing domain rules.

The adapter boundary is intentionally concrete. A future `pitblu-blower-core` is a
separate sibling with its own safety and control loop; no blower or generic hardware
plugin framework is implemented here.

The delivered scope and final real-device verification are recorded in the
[Milestone 1 acceptance record](../docs/pitblue-app-milestone-1.md).
