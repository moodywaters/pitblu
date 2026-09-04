# ADR 0003: Separate REST transport from persistent administration

- Status: accepted
- Date: 4 September 2026

## Decision

Use FastAPI as a thin REST transport over an administration service. Track slow actions as
persistent operation resources and run their device work in background asyncio tasks. Store only
administrative state in SQLite; keep current telemetry snapshots in memory.

Layer configuration from defaults, YAML, environment and persisted overrides. Validate the whole
effective Pydantic model before a transactional update and use version ETags for concurrency.
Require bearer authentication outside loopback, persist only salted scrypt token hashes, and place
integration secrets behind write-only resources.

## Consequences

OpenAPI clients do not depend on Bleak or SQLite details. A process interruption leaves useful
operation metadata and desired device state without creating a cook-history database. Configuration
updates cannot partially apply or silently overwrite a concurrent change. Secret-bearing request
validation cannot echo submitted values.

The v0.5.0 resilience controller will add per-device operation serialisation, recovery and bounded
operational events. The v0.6.0 installer will provision database permissions and the initial token.
