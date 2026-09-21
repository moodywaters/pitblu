# pitblu-app API and integration guide

## Core thermometer heartbeat boundary

pitblu-core device responses carry the session-scoped `heartbeat` object and emit
`thermometer.heartbeat`. The core client may use this to distinguish a reachable gateway from a
responding thermometer. It must preserve the meanings documented in
[thermometer heartbeat](thermometer-heartbeat.md): service availability, device connection,
communication heartbeat, and probe freshness are separate. After a core SSE reconnect, reconcile
device state through core REST before applying current-session heartbeat events. The application
must never initiate recovery merely because the heartbeat is stale; operator reconnect continues
through the core REST operation.

`pitblu-app` is Pitblu's API-first cook service. The official operator, display
and follower screens use this same `/api/v1` contract. A browser is not required
for telemetry recording, alert evaluation or cook lifecycle state.

## Authentication and client roles

Except for `/health`, follower capability routes and follower QR images, clients
send an opaque application token in the HTTP header:

```http
Authorization: Bearer <application-token>
```

Never place an operator, display or integration token in a URL. Configure distinct
values of at least 32 characters through `PITBLU_APP_OPERATOR_TOKEN`,
`PITBLU_APP_DISPLAY_TOKEN` and, when needed,
`PITBLU_APP_INTEGRATION_TOKEN`.

| Credential | Intended client | Access |
| --- | --- | --- |
| Operator | Phone, tablet or laptop operator | Full cook API |
| Display | Permanent Pitblu display | Read-only state, default follower QR information and streams |
| Integration | Node-RED or a future physical control | Reads plus events, alert acknowledgement and lifecycle actions |
| Follower capability | Guest follower link | Read-only access to one active Cook |

An integration token cannot change Cook structure, assignments, targets or shares.
A display token cannot create, regenerate, revoke or update a follower share.
A follower capability cannot be promoted by supplying another credential and
expires when its Cook closes. Treat every token and follower URL as a secret.

## Contract discovery

Reusable equipment is managed through `GET/POST /api/v1/cooker-profiles` and
`PATCH /api/v1/cooker-profiles/{id}`. `POST /api/v1/cooks` accepts an optional
`cookerProfileId`; the selected profile is snapshotted into the Cook. This keeps
equipment setup reusable while preserving historical names and relationships.

Authenticated OpenAPI is available at `/openapi.json`; interactive documentation
is at `/docs`. OpenAPI marks bearer-protected and public capability operations.
All error responses use a stable envelope containing `code`, `message` and a
`correlationId`. Validation errors also contain structured `details`.

The main resources are:

- `/api/v1/system`, `/api/v1/cooks` and Cook detail;
- Cook-scoped `cookers`, `food-items`, `measurements` and `assignments`;
- Cook-scoped `telemetry`, `events` and `shares`;
- `/api/v1/alerts` and alert acknowledgement;
- explicit Cook lifecycle actions: `start`, `finish-cooking`, `start-rest`,
  `serve` and `close`;
- `/api/v1/events` for the authenticated application event stream.

Use the exact schemas in OpenAPI rather than relying on this overview.

## Default Live Display follower share

When a Cook enters the active state, the backend ensures it has exactly one active
default follower share. A display reads it with
`GET /api/v1/cooks/{cookId}/default-share` and renders the returned QR path. This
read may repair a missing invariant server-side; the display itself never submits a
share mutation. Closing the Cook expires all of its follower shares.

Operators can still create additional shares with `POST /api/v1/cooks/{cookId}/shares`,
revoke any share with `DELETE /api/v1/shares/{shareId}`, or deliberately replace the
default capability with `POST /api/v1/cooks/{cookId}/default-share/regenerate`.
Regeneration immediately invalidates the previous follower URL.

## Event writes and retries

To record an operator or physical-control action, post a Cook Event using an
integration or operator token. Supply a stable `Idempotency-Key` when the caller
may retry an uncertain request:

```http
POST /api/v1/cooks/{cookId}/events
Authorization: Bearer <integration-token>
Content-Type: application/json
Idempotency-Key: <caller-generated-unique-id>

{"type":"added_fuel"}
```

Reusing the key for the same Cook returns the already-recorded event instead of
creating a duplicate. Lifecycle actions are also safe to retry when the Cook is
already in the requested resulting state.

## Live events

Connect to `/api/v1/events` with a bearer header using an SSE-capable HTTP client
or authenticated fetch stream. Do not put the token in the query string. SSE has
no replay guarantee: after connecting or reconnecting, fetch authoritative REST
state and use live events as invalidation signals. Event frames include `eventId`,
`type`, `occurredAt` and structured `data`.

Follower clients instead use `/api/v1/follow/{token}/stream`; that stream is
filtered to the shared Cook. A revoked or closed-Cook capability no longer grants
REST access or a new stream connection.

## Thermometer boundary

External clients integrate with `pitblu-app`, not `pitblu-core`, for Cook-aware
meaning and actions. The app alone holds the core administrator credential and
consumes core REST/SSE through its thermometer adapter. A physical source is the
pair `(coreDeviceId, probeChannel)`; semantic meaning comes from the time-bound
Probe Assignment stored with each historical reading.
