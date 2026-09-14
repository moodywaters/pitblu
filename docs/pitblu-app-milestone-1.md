# pitblu-app Milestone 1 acceptance

Milestone 1 implementation is complete and is ready for an end-to-end Cook on a
trusted LAN. This record separates repeatable software verification from the final
site-specific check with a real thermometer and display.

## Delivered

- Platform-neutral FastAPI service using only pitblu-core REST and SSE through a
  concrete `PitbluCoreClient` boundary. No Bluetooth, GPIO, Raspberry Pi, ARM or
  blower dependency exists in pitblu-app.
- First-class Windows development with the app backend, Vite and a local SQLite
  database consuming either a real authenticated Pi-hosted Core over the LAN or
  an optional local simulated Core through the identical configured boundary.
- Versioned REST, OpenAPI and application SSE for all Cook, setup, lifecycle,
  telemetry, event, Alert, history and follower capabilities.
- SQLite migrations and a collection-based domain. A physical source is always a
  `(coreDeviceId, probeChannel)` pair; time-bound assignments preserve semantic
  measurement history through live reassignment.
- Backend-owned targets, ranges, persistence, interpreted state and stateful Alerts.
  Core observation time, unavailable samples and graph gaps are preserved.
- React, TypeScript and PWA operator, Live Display and follower surfaces. The build
  is served as static files by FastAPI; production does not require Node.
- Bearer-scoped operator and strictly read-only display access. Backend lifecycle
  owns the default follower capability; closing a Cook expires its links.
- Discreet GitHub provenance on public views and a graceful expired-follower view.
- CI gates on Python 3.11–3.13 plus TypeScript, React tests, the production PWA build,
  and verification that the built UI is included in the Python wheel.

The future blower seam remains a separate sibling client for
`pitblu-blower-core`. No blower behavior, generic plugin framework or actuator
abstraction has been added.

## Automated acceptance

The suite covers domain lifecycle, multiple device identities using the same probe
channel, reassignment history, telemetry gaps, stale/unavailable behavior, Alerts,
SSE, authentication scopes, default-share reconciliation and expiry, browser loss
through backend persistence, display/follower read-only behavior, and thermometer
disconnect/reconnect REST reconciliation.

Run the complete repeatable gate from `pitblu-app`:

```text
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m ruff format --check src tests
..\.venv\Scripts\python.exe -m mypy src
..\.venv\Scripts\python.exe -m pytest
cd frontend
npm ci
npm run build
npm test
```

## Physical acceptance still to record

Before calling a particular installation operationally accepted, run one real Cook
journey with its deployed pitblu-core, browser devices and LAN. Confirm probe
readings, phone/tablet layout, a permanently running `/display`, QR scanning from a
guest phone, a physical disconnect/reconnect gap, and restart recovery. This is an
environment acceptance check, not missing Milestone 1 application functionality.

Use the deployment and test instructions in
[the pitblu-app README](../pitblu-app/README.md). Do not expose the application or
follower URLs to the public internet.
