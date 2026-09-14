# ADR 0006: React, TypeScript and PWA frontend

**Status:** Accepted

## Context

The first `pitblu-app` browser client proved the API-first operator, display and
follower journeys with dependency-free JavaScript. It is not intended to become
the long-term interface foundation. Pitblu needs typed API payloads, reusable
responsive components and an installable application while retaining a small
operational footprint.

## Decision

Use React 19 and TypeScript 6, built by Vite 8. `vite-plugin-pwa` generates the web
manifest and service worker. Vitest, jsdom and Testing Library cover frontend API,
authentication and component behavior. No client router, global state framework,
server-side JavaScript framework or component suite is introduced.

Frontend source is isolated from the Python package:

```text
pitblu-app/
  frontend/
    src/
      api/          typed REST and authenticated SSE client
      components/   shared presentation components
      surfaces/     operator, display and follower composition
      types/        API and application-event contracts
    public/         install icons and other copied assets
    index.html
    package.json
    tsconfig.json
    vite.config.ts
  src/pitblu_app/static/  generated production assets only
```

During development, Vite provides hot module replacement and proxies `/api`,
`/health`, `/ready` and follower requests to FastAPI. Both processes are development
tools. `npm run build` type-checks and produces versioned static assets directly in
`src/pitblu_app/static`. The Python wheel includes those assets, and FastAPI alone
serves them in production. Node.js is therefore a build dependency, not a runtime
or deployment architecture requirement.

The operator and Live Display ask for their respective bearer tokens and retain
them in `sessionStorage`. Typed `fetch` supplies the `Authorization` header for
REST and an authenticated fetch-stream parser supplies it for SSE. Tokens are never
placed in URLs. Follower URLs remain separate read-only capabilities and may use
native `EventSource` because the capability is already the scoped URL. The browser
never receives the `pitblu-core` credential.

The Live Display reads its default follower capability after Cook activation. That
capability is created and repaired by the backend Cook lifecycle; display scope has
no share mutation permission.

React owns rendering, navigation selection, temporary form state and reconnection.
FastAPI remains authoritative for Cooks, lifecycle, assignments, interpretation,
alerts, history, sharing and permissions. TypeScript interfaces describe API and
SSE payloads; they do not reproduce domain rules.

The prototype's user journeys, CSS identity and API interaction behavior are the
functional reference. They are ported incrementally. Its handwritten DOM renderer
and production files are removed after the React build achieves parity; no second
client is retained.

## Consequences

- Production remains a single platform-neutral Python service.
- Frontend compile errors and component tests catch contract drift earlier.
- Operator, display and follower surfaces share typed clients and components while
  retaining distinct permissions and presentation.
- Offline support covers the application shell only. Dynamic Cook data is not
  cached as authoritative state and the UI clearly requires connectivity for live
  operation.
