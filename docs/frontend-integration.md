# Frontend and AI integration guide

Contract baseline: released `v0.6.0`. This guide describes the implementation, not a
promise that every item in the project plan already exists. Recheck it against the
installed version before building a client. The v0.9.0 audit and v1.0.0 physical
acceptance, including the minimum 16-hour soak, are separate release gates.

Development branch only: [unreleased changes](unreleased.md) document fixes to
partial device updates and browser response headers. The v0.6.0 caveats below still
apply to the released Pi installation until an explicitly validated upgrade.

Additional unreleased settings are `security.auth_requests_per_minute`,
`security.mutations_per_minute`, `security.maximum_body_bytes` and
`security.maximum_sse_clients`. These do not exist in the released v0.6.0 API.
The development branch also protects `GET /openapi.json`, `GET /docs` and
`GET /redoc` with the configured authentication policy; released v0.6.0 leaves
these documentation routes public.

## 1. Purpose and architecture

`pitblu-core` is a native Raspberry Pi hardware gateway. It discovers and manages
Weber iGrill V202 devices, reads up to four probe channels and battery state, exposes
administration through REST, and publishes current telemetry through SSE and MQTT.
It has no browser UI, cook sessions, temperature history, graphs, alarms, food names,
probe roles or notifications. A separate application must own those features and its
own database. Do not add cook semantics to the gateway or use its SQLite database as
an integration interface.

Recommended arrangement:

```text
Browser -> separate web application's backend -> pitblu-core REST and SSE
                                             -> MQTT broker (read-only subscription)
                                             -> web application's own history database
pitblu-core -> Bluetooth iGrill
             -> MQTT broker
```

Keep the gateway administrator token in the web backend's protected credentials,
not browser storage, JavaScript bundles, URLs or logs. Give the web application its
own least-privilege MQTT subscriber identity. Do not reuse the gateway publisher's
credentials. REST is the only command interface; MQTT never accepts commands.

The gateway defaults to port 8080 and loopback. `127.0.0.1` refers to the machine
making a request, not automatically to the Pi. A backend elsewhere needs explicitly
configured trusted-LAN reachability and token authentication. No built-in HTTPS or
MQTT-over-WebSocket endpoint is provided by the gateway. Never expose it directly
to the internet. A public-facing web application must provide its own authentication,
authorisation, secure transport and controlled backend access to the private gateway.

## 2. Contract discovery and authentication

- Read `/api/v1/status` for the package version and current `sessionId`.
- `/openapi.json`, `/docs` and `/redoc` expose generated API documentation. These
  documentation routes are currently unauthenticated; they are not credentials or
  current-state endpoints.
- OpenAPI describes request models but many responses are generic dictionaries.
  Use the response shapes and behaviour below as well as the generated schema.
- `GET /health` needs no authentication. With `auth.mode=token`, every `/api/v1/*`
  endpoint and `/ready` needs `Authorization: Bearer <administrator-token>`.
- Package development defaults allow disabled authentication only on loopback.
  The managed native installation requires token authentication even on loopback.
- There is one administrator credential, not user accounts, roles, read-only API
  tokens or OAuth. The web backend must enforce its own user permissions.
- `POST /api/v1/auth/token/rotate`, with the current token and no body, returns
  `{"token":"<replacement>"}`. The previous token is invalid immediately for new
  requests. Securely save the replacement and update all authorised clients.
  Never automatically retry rotation after an ambiguous network failure: the old
  token may already have been invalidated. Operator recovery may be needed.
- An already-open SSE connection is authenticated at connection time, not per event.
  Rotation does not itself close that connection.

Native installation displays its initial token once. There is no token-read endpoint.
The gateway stores only a salted token hash. MQTT passwords are write-only but stored
in the protected administrative database; do not treat backups as non-sensitive.

## 3. Complete HTTP resource inventory

All paths below other than the three explicit root paths begin with `/api/v1`.
Successful reads and updates return 200 unless another status is shown. Send JSON
request bodies with `Content-Type: application/json`; unknown model fields are rejected.

| Method and path | Request / result |
| --- | --- |
| `GET /health` | `{"status":"ok"}`: process liveness only. |
| `GET /ready` | `{"status":"ready"}` (200), or `{"status":"not_ready"}` (503) when enabled MQTT is not connected. |
| `GET /api/v1/status` | Version, UTC time, session, MQTT and device-runtime diagnostics. |
| `GET /api/v1/diagnostics` | Same result as status. |
| `GET /api/v1/bluetooth` | `available`, `connected`, `source`; see limitations below. |
| `POST /api/v1/scans` | `{}` or `{"duration":5}`; 202 operation. Duration must be greater than 0 and at most 60 seconds. |
| `GET /api/v1/scans/{scanId}` | Operation fields plus `devices` discovery array. |
| `GET /api/v1/devices` | Array of registered device objects. |
| `POST /api/v1/devices` | Registration body below; 201 device, or `{device,operation}` when `connect=true`. |
| `GET /api/v1/devices/{deviceId}` | Registered device object. |
| `PATCH /api/v1/devices/{deviceId}` | Optional `friendlyName`, `automaticReconnection`, `discoveryId`; returns device. See PATCH caveat below. |
| `DELETE /api/v1/devices/{deviceId}` | Disconnects and unregisters; 204, no response body. |
| `POST /api/v1/devices/{deviceId}/connect` | No body; 202 operation. |
| `POST /api/v1/devices/{deviceId}/disconnect` | No body; 202 operation. |
| `POST /api/v1/devices/{deviceId}/reconnect` | No body; 202 operation; bypasses recovery backoff. |
| `GET /api/v1/devices/{deviceId}/probes` | Probe array, or `[]` before the first snapshot. |
| `GET /api/v1/devices/{deviceId}/battery` | Battery object, or JSON `null` before the first snapshot. |
| `GET /api/v1/operations` | Bounded array of recent persistent operations. |
| `GET /api/v1/operations/{operationId}` | One operation, or 404 if absent/evicted. |
| `GET /api/v1/events` | Up to 100 in-memory canonical events, oldest to newest. |
| `GET /api/v1/events/operations` | Up to 100 persistent operation/configuration events, not temperature history. |
| `GET /api/v1/events/stream` | Authenticated live SSE stream. |
| `GET /api/v1/config` | Configuration metadata, version, secret status; quoted `ETag` response header. |
| `GET /api/v1/config/schema` | Same descriptive body, not JSON Schema; no ETag header is set here. |
| `POST /api/v1/config/validate` | `{"values":{...}}`; validates proposed combined configuration; returns `{"valid":true}`. |
| `PATCH /api/v1/config` | `{"values":{...}}` and `If-Match`; atomic save, returns updated body and ETag. |
| `PUT /api/v1/config/secrets/mqtt.password` | `{"value":"<secret>"}`; returns name, configured=true, changedAt. |
| `DELETE /api/v1/config/secrets/mqtt.password` | No body; returns name, configured=false, changedAt=null. |
| `POST /api/v1/auth/token/rotate` | No body; returns replacement token once. |

There are no pagination parameters, filtering endpoints, operation-cancellation
endpoint, service-restart endpoint, firmware-update endpoint or history-query API.

## 4. Discovery, registration and connection workflow

1. List registered devices before offering onboarding; do not auto-register every
   nearby device or infer identity from the advertised name.
2. Start a scan with `{}` and retain the returned `operationId`.
3. Poll `/scans/{operationId}` until `succeeded` or `failed`. A scan can wait for
   other Bluetooth work, so its HTTP completion time is not just its scan duration.
4. On success, let the user select a result shaped as
   `{"discoveryId":"<opaque>","name":"iGrill_V202-EXAMPLE","model":"igrill-v202","rssi":-60}`.
   Handle absent signal-strength data. Discovery IDs are temporary and can expire
   after another background or manual scan. Rescan on an expired-result conflict.
5. Register promptly using the selected ID:

```json
{
  "discoveryId": "<opaque ID returned by scan>",
  "friendlyName": "Garden thermometer",
  "connect": true,
  "automaticReconnection": true
}
```

`discoveryId` is required and non-empty. `friendlyName` is nullable and at most 100
characters. `connect` defaults to false; `automaticReconnection` defaults to true.
Do not submit a Bluetooth address, invent an ID or assume the example name exists.

A device object has this shape:

```json
{
  "deviceId": "igrill-v202-example",
  "name": "iGrill_V202-EXAMPLE",
  "friendlyName": "Garden thermometer",
  "model": "igrill-v202",
  "automaticReconnection": true,
  "desiredState": "connected",
  "observedState": "polling",
  "createdAt": "2026-09-07T12:00:00+00:00"
}
```

Use the returned public `deviceId` in URLs and in your database; it is stable across
restarts. Encode path segments. Friendly names are labels, not identity. Treat all
names as untrusted display text and escape them, never render as raw HTML.

Registration with `connect=true` returns `{device,operation}`; without it, the
response is the device object directly. Registration can succeed before connection
fails. After a lost response or conflict, list devices before trying again.

The implementation currently owns one active adapter/device at a time, even though
the registry is a collection. Switching devices requires disconnecting the current
owner. Simultaneous multi-thermometer polling is not supported.

Device PATCH caveat: in v0.6.0, omitting `friendlyName` clears it to null. Include the
existing name when only changing `automaticReconnection` or `discoveryId`. Identity
selection requires disconnection first and a fresh discovery result. This is useful
for legacy registrations without a saved identity; do not silently rebind hardware.
Changing automatic reconnection is not equivalent to a connect/disconnect command.

Explicit disconnect persists desired state `disconnected` and cancels recovery.
Automatic recovery on startup requires both desired state `connected` and automatic
reconnection enabled. Desired state expresses user intent; observed state describes
the current outcome. Render them separately. The state vocabulary includes
`discovered`, `connecting`, `initialising`, `connected`, `polling`, `degraded`,
`backoff`, `disconnected`, `unsupported`; short-lived internal states may not be
observable through every transport. Do not require every transition to appear.

## 5. Asynchronous operations and errors

```json
{
  "operationId": "<opaque operation ID>",
  "kind": "connect",
  "deviceId": "igrill-v202-example",
  "status": "queued",
  "createdAt": "2026-09-07T12:00:00+00:00",
  "updatedAt": "2026-09-07T12:00:00+00:00",
  "errorCode": null
}
```

Kinds include scan/connect/disconnect/reconnect. Scan has null `deviceId`. Status is
`queued`, `running`, `succeeded` or `failed`. HTTP 202 only acknowledges the operation;
it is not evidence of a working probe. Poll its resource with a bounded deadline
and modest interval (for example one second), then refresh device and telemetry.
SSE operation events can accelerate refresh but cannot replace reconciliation.

An identical pending connection action returns the existing operation; conflicting
pending actions return 409. Repeated connect/disconnect is idempotent in resulting
state, not necessarily operation ID. Concurrent scan requests share a pending scan.
There is no arbitrary idempotency-key contract. Do not blindly retry registration,
token rotation or other mutations after an uncertain response.

Operations are capped at 100. Interrupted work can become failed with `interrupted`;
normal device failures use `device_operation_failed`. Consult safe diagnostics and
refresh state rather than displaying invented causes. Historical scan operation
metadata can survive restart while its in-memory discovery results do not.

Handled errors use:

```json
{"error":{"code":"state_conflict","message":"...","correlationId":"..."}}
```

`details` may contain safe validation fields (`type`, `location`, `message`). Common
statuses: 401 `authentication_required`, 404 `not_found`, 409 `state_conflict`,
422 `validation_error`, 500 `internal_error`. Framework routing errors, network
failures or proxy responses need not have this envelope. Handle non-JSON responses.
Do not log request bodies, Authorization headers or secret response values.
`X-Correlation-ID` is returned and can be supplied by a backend for request tracking;
it is not an operation ID and is not automatically present in operation resources.

## 6. Current readings and health semantics

Probe objects contain `probe` (1 to 4), `available`, `present`, `fresh`,
`temperatureC` (number or null), `observedAt` (UTC ISO 8601), `sequence`,
`source` (`physical` or `simulated`) and nullable `errorCode`.

```json
{"probe":1,"available":true,"present":true,"fresh":true,"temperatureC":21.0,"observedAt":"2026-09-07T12:00:00+00:00","sequence":9,"source":"physical","errorCode":null}
```

Battery objects contain `available`, `fresh`, `percentage` (number or null),
`observedAt`, `sequence`, `source`. `null` battery and an empty probe array mean no
snapshot yet, not zero battery or zero degrees. A readable empty probe socket can
report `available=true`, `present=false`, `fresh=true`, `temperatureC=null`.
Display a numeric probe value only when available, present, fresh and non-null.
Zero is a valid numeric value; never use truthiness to test temperature availability.

When stale, REST suppresses numeric temperature and battery values, retains their
last observation metadata, and marks freshness/availability false. Probe errorCode
is then `stale`. Explicit disconnect also invalidates readings. Keep any last-known
value only as visibly historical in your application's state, never as live data.
Allow unknown error codes without crashing. Always mark simulated data prominently.

Status returns `status`, `version`, `time`, `sessionId`, `mqtt`, `deviceRuntime`.
MQTT disabled is `{"state":"disabled"}`; otherwise fields are `state`, cumulative
`failures`, nullable `errorCode`, nullable `retryIn` (scheduled backoff seconds, not
a live countdown). States include starting/connecting/connected/backoff/stopped.
Device-runtime fields are `stopping`, `connected`, `pollingTasks`, `recoveryTasks`,
`pendingOperations`, `errorCode`, `failureStage`, `discoveryErrorCode`.

Top-level `status=ok` and `/ready` 200 do not prove thermometer availability: readiness
currently checks only enabled MQTT connectivity. `/bluetooth` currently returns
`available=true` without independently checking adapter power or radio health.
Show process, broker, device, probe presence and reading freshness separately.
There is currently no clock-synchronisation-health field. Use receipt times and
connection health as well as UTC timestamps when deciding whether data is live.

## 7. SSE: live event integration

Connect to `GET /api/v1/events/stream` with the bearer header. The browser's native
EventSource cannot attach an arbitrary Authorization header: use your backend relay
or an authenticated fetch-stream parser. Do not put the token in a query string.
Parse full SSE framing, including partial network chunks, blank-line delimiters,
named events and comment heartbeats. Example:

```text
id: <unique event ID>
event: probe.temperature
data: {"schemaVersion":1,"eventId":"<unique event ID>","sessionId":"<process session>","type":"probe.temperature","observedAt":"2026-09-07T12:00:00+00:00","sequence":9,"source":"physical","deviceId":"igrill-v202-example","probe":1,"data":{"temperatureC":21.0}}

```

All canonical events have schemaVersion, eventId, sessionId, type, observedAt,
sequence, source, deviceId, probe and data. Non-applicable deviceId/probe can be null.

| Event type | Type-specific `data` |
| --- | --- |
| `service.availability` | `available` boolean. |
| `device.availability` | `available`, optional `reason` such as stale/disconnected. |
| `device.connection` | `state`. |
| `device.battery` | `available`, `percentage`, optional `reason`. |
| `probe.availability` | `available`, `present`, optional `reason`. |
| `probe.temperature` | `temperatureC`. |
| `operation.state` | `operationId`, `kind`, `status`, `errorCode`. |
| `configuration.changed` | Configuration `version` and changed `settings` names, no values or secrets. |

The stream is live-only: no initial snapshot, Last-Event-ID replay or durable cursor.
Each subscriber queue is bounded to 100; the oldest queued event is dropped on
overflow. `/events` is also bounded in memory, not a replay guarantee. Secret writes
and token rotation do not emit configuration.changed events in this release.

On initial load or reconnect, attach the stream, buffer incoming events while
fetching REST snapshots, reconcile by resource/observation time, then continue live.
There is no atomic cross-resource snapshot or cross-transport sequence contract;
periodically reconcile from REST and refetch on uncertainty. If the stream closes,
mark the connection interrupted, reconnect with capped backoff, and refresh REST.
Treat a new sessionId as a process restart, not a continuation of old counters.
An idle `: heartbeat` comment is transport activity, not a fresh probe sample.
Do not expect a final offline SSE event: streams close before full service shutdown.

## 8. MQTT: complete subscriber contract

Use the configured base topic, not a hard-coded validation topic. Let `B` be
`mqtt.base_topic` with leading/trailing slashes removed. REST version and MQTT schema
version are independent. Subscribe with QoS 1 for the gateway's QoS 1 publications.

| Topic | Retained | Payload-specific fields |
| --- | --- | --- |
| `B/v1/service/availability` | Yes, Last Will | `available` |
| `B/v1/devices/{deviceId}/availability` | Yes | `available`, optional `reason` |
| `B/v1/devices/{deviceId}/connection` | Yes | `state` |
| `B/v1/devices/{deviceId}/battery` | Yes | `available`, `percentage`, optional `reason` |
| `B/v1/devices/{deviceId}/probes/{probe}/availability` | Yes | `available`, `present`, optional `reason` |
| `B/v1/devices/{deviceId}/probes/{probe}/temperature` | No | `temperatureC` |

Every JSON payload includes `schemaVersion:1`, `observedAt`, `sequence`, `source`,
and, in the running service, `sessionId`. Device/probe fields are included where
applicable. Unlike SSE, MQTT flattens type-specific fields into the top-level object
and omits eventId/type/data. Operation and configuration events are not published.

```json
{"schemaVersion":1,"observedAt":"2026-09-07T12:00:00+00:00","sequence":9,"source":"physical","sessionId":"<process session>","deviceId":"igrill-v202-example","probe":1,"temperatureC":21.0}
```

Useful subscriptions: `B/v1/devices/+/probes/+/temperature` for temperatures,
`B/v1/#` for the whole telemetry tree. There is no wildcard API administration.
Use separate base topics for separate gateway instances and tests to avoid collisions.

QoS 1 allows duplicates. For device telemetry, scope ordering/deduplication by
gateway, sessionId and full topic, then sequence. Do not compare counters across
topics or between REST and MQTT. Service availability is an important exception:
online heartbeats/reconnections reuse sequence 1 and offline messages use sequence 2
within a session. A subscriber must not discard a later online state just because
its sequence is less than a previous offline state; process service-state arrivals
and maintain receipt time. Event operation sequences are also not global counters.

Retained means broker-cached state, not necessarily fresh or currently connected.
Combine service availability, device/probe availability, source, session and local
receipt/freshness timers. On broker reconnect, the publisher replays latest retained
state but never historical temperatures. Newly subscribed clients can use REST for
initial readings and wait for subsequent non-retained temperature publications.
No temperature is sent for an absent/invalid probe; availability must clear the UI.

The Last Will timestamp is prepared at connection time, not crash time. Record
receipt time to detect loss. Normal shutdown publishes current offline availability.
Broker-loss detection may wait until a publish/idle heartbeat; do not promise instant
failure detection. Retained messages for deleted devices or old base topics are not
purged automatically: use REST registration as the authority for what is managed,
not the presence of an old broker topic. Broker cleanup is an operator concern.

## 9. Configuration editor and secrets

Use GET `/config` to build the settings UI. Body keys are `version`, `settings`
(flat dotted-name map) and `secrets`. Each setting has value, source, type,
description, default, minimum, maximum, allowed, editable, sensitive,
restartRequired. Sources are `default`, `yaml`, `environment`, `persisted_override`,
in increasing precedence. Metadata currently uses Python type names, not JSON Schema;
for example nullable mqtt.username has default type `NoneType`. Timing minimum 0
means strictly greater than zero. Validate through the API, not metadata alone.

| Setting | Default | Constraint / purpose |
| --- | --- | --- |
| `server.bind` | `127.0.0.1` | `127.0.0.1` or `0.0.0.0`; LAN requires token mode. |
| `server.port` | 8080 | Integer 1..65535. |
| `server.cors_origins` | `[]` | Array of explicitly authorised browser origins. |
| `auth.mode` | `disabled` | disabled/token; managed installation requires token. |
| `bluetooth.scan_duration` | 5 | Seconds, >0..60. |
| `bluetooth.missing_scan_interval` | 15 | Seconds, >0..3600. |
| `bluetooth.connected_scan_interval` | 60 | Seconds, >0..3600. |
| `bluetooth.connect_timeout` | 10 | Seconds, >0..120. |
| `bluetooth.initialise_timeout` | 15 | Seconds, >0..120. |
| `bluetooth.read_timeout` | 5 | Seconds, >0..60. |
| `polling.probe_interval` | 5 | Seconds, >0..300; work duration can lengthen observed cadence. |
| `polling.battery_interval` | 300 | Seconds, >0..3600; currently not wired to a separate schedule. |
| `polling.stale_after` | 15 | Seconds, >0..3600. |
| `polling.degraded_after_failures` | 3 | Integer 1..100 failed cycles. |
| `polling.forced_reconnect_after` | 30 | Seconds, >0..3600 without valid readings. |
| `polling.availability_heartbeat` | 60 | Seconds, >0..3600; SSE idle comments/MQTT idle heartbeat. |
| `polling.stable_backoff_reset` | 60 | Seconds, >0..3600. |
| `mqtt.enabled` | false | Enable publisher. |
| `mqtt.host` | `127.0.0.1` | Non-empty string, at most 253 characters. |
| `mqtt.port` | 1883 | Integer 1..65535; configure TLS port explicitly. |
| `mqtt.tls` | false | System-trust TLS; no client certificate/custom CA API. |
| `mqtt.username` | null | Nullable string, at most 128 characters. |
| `mqtt.base_topic` | `pitblu` | 1..128 characters; no +, # or NUL. |
| `mqtt.qos` | 1 | Fixed at 1. |
| `simulation.enabled` | false | Select simulator instead of physical adapter. |
| `simulation.probe_count` | 4 | Integer 1..4. |

All settings currently report restartRequired=true. Saving changes updates the
configuration API's view immediately, but running workers/listener/authentication
retain startup settings until restart. Label changes as saved/pending restart;
do not report them as applied to the running hardware merely because GET reflects
the new value. No REST endpoint restarts the service and there is no active-versus-
pending diff endpoint. Coordinate restart with an operator, never during an active
cook without their approval. Changing bind/port/authentication can affect reachability.

Example transaction:

```http
GET /api/v1/config
Authorization: Bearer <token>

POST /api/v1/config/validate
Authorization: Bearer <token>
Content-Type: application/json

{"values":{"polling.probe_interval":5,"mqtt.enabled":true}}

PATCH /api/v1/config
Authorization: Bearer <token>
Content-Type: application/json
If-Match: "<version from GET>"

{"values":{"polling.probe_interval":5,"mqtt.enabled":true}}
```

The actual If-Match value is the quoted numeric ETag, for example `"3"`, not the
placeholder above. Missing/invalid/stale versions return 409. On conflict, refetch
and ask the user to reconcile changes; never overwrite another editor silently.
Validation does not reserve a version or test broker/hardware connectivity. No API
removes a persisted override to reveal a lower layer; writing the default still
creates an override. Null is not a general reset instruction.

Only `mqtt.password` is supported by secret routes. PUT accepts a non-empty string
up to 4096 characters. A configured=true response proves storage, not successful
broker authentication. Password changes/deletion also need a restart for the running
publisher. Secret writes do not use If-Match or increment the configuration version.
Show a masked empty input with configured/not-configured status; never prefill a
fake mask as the password or submit it when unchanged. Rotation is separate from
configuration and takes effect immediately for new authenticated requests.

CORS is disabled by default. Configured CORS permits GET/POST/PATCH/PUT/DELETE and
Authorization/Content-Type/If-Match headers. It currently does not expose ETag or
X-Correlation-ID response headers to cross-origin browser JavaScript, nor allow
X-Correlation-ID in preflight. A same-origin backend relay avoids these limitations
and keeps the administrator credential out of the browser. Do not assume enabling
CORS supplies end-user authentication or secure transport.

## 10. Suggested web application coverage

Provide a gateway health panel; a registered-device list; explicit scan/select/add
workflow; editable friendly names and recovery preference; connect/disconnect/
reconnect/delete with confirmation; four probe tiles; battery and freshness; an
operation progress/error panel; recent operational events; live stream status;
a schema-driven configuration editor with version-conflict handling and pending-
restart notices; write-only MQTT password management; and protected token rotation.

Persist your own probe-to-cook mapping, historical samples, alarms and user settings.
Use a chosen primary ingest transport for history, rather than double-counting SSE
and MQTT copies. Mark gaps explicitly. The gateway does not backfill telemetry lost
while your backend was disconnected and is not a safety-certified cooking alarm.

Simulation is selectable through configuration, but its advanced fault/pattern
controls are internal testing interfaces, not exposed REST controls. Do not invent
UI buttons for scripted insertion/removal or failure injection without adding a
separate, deliberately scoped test facility.

## 11. Acceptance checklist for an AI-built frontend

- Every route above has an intentional UI/backend use or a documented reason to omit it.
- No gateway or broker credentials reach browser assets, URLs, logs or analytics.
- Scan expiry, duplicate registration, pending-operation conflicts and 404 eviction work.
- Empty snapshots, zero degrees, absent sockets, stale values and simulated data display correctly.
- Broker failure, BLE loss and web-backend loss have distinct indicators.
- New sessions, duplicate MQTT delivery, service sequence reuse and stale retained messages work.
- SSE reconnection refetches state; gaps never become invented historical samples.
- Config conflicts preserve edits, secret masks are not submitted, and restart requirements are clear.
- Token rotation handles the one-time result and ambiguous failures safely.
- Readiness is not presented as proof of connected hardware or fresh temperatures.
- Destructive administration and service maintenance cannot happen accidentally during a cook.

## 12. Sources and maintenance

For the cook's perspective, also read [Pitblu in plain English](bbq-overview.md)
and [Quick start for a cook](bbq-quick-start.md). Keep user-facing explanations
consistent with these guides, without implying a dashboard or alarms already exist.

Implementation sources: `pitblu-core/src/pitblu_core/api.py`, `configuration.py`, `service.py`,
`telemetry.py`, `events.py`, `mqtt.py`, `auth.py` and the adapter implementations.
Read alongside [REST API](api.md), [configuration](configuration.md),
[MQTT](mqtt.md), [installation](installation.md), [troubleshooting](troubleshooting.md)
and [physical acceptance](physical-acceptance.md).

When changing a route, request/response field, event, topic, authentication behaviour
or configuration setting, update this guide in the same change. Do not silently
turn implementation gaps into promises. In particular the separate battery cadence,
clock-synchronisation diagnostics, browser integration limitations and device PATCH
semantics noted here remain audit items until code and tests demonstrate a fix.
