# Changelog

All notable changes will be documented here.

## [Unreleased]

### v0.5.0 candidate

- Supervised MQTT retry, stable-period backoff reset, retained-state replay and safe publisher status.
- BLE retry after connection loss or sustained invalid reads, with explicit reconnect bypass.
- Protected registered device identity, additive SQLite migration and restart recovery.
- Duplicate-operation reuse, conflict rejection, single-adapter ownership and serialised BLE calls.
- Bounded persistent operation events, configuration-change events and interrupted-operation recovery.
- Authenticated diagnostics, MQTT-aware readiness and session identifiers in telemetry.
- Immediate disconnect invalidation, stale retained battery state and duplicate-snapshot suppression.
- Graceful shutdown flushes unavailable state and cancels recovery without clearing desired state.
- Close SSE responses before HTTP shutdown drainage, without interrupting final MQTT publications.
- Recover a registered device's leftover BlueZ connection after unexpected process termination.

Raspberry Pi resilience acceptance is pending. v0.5.0 has not been released.

## [0.4.0] - 2026-09-05

### Added

- Canonical version-one telemetry events with bounded in-memory fan-out and history.
- Authenticated SSE stream with event identifiers and idle heartbeats.
- Configurable MQTT publisher, QoS 1 topic mapping and retained service Last Will.
- Continuous connected-device sampling through the shared physical/simulated adapter path.
- Configurable stale-reading transitions reflected in REST, SSE and MQTT availability.

### Fixed during Raspberry Pi validation

- Preserve internal device identifiers and observation timestamps when constructing events.
- Use the current observation time for live simulator samples, including delayed connections.

### Validated

- Hardware-independent MQTT topic, payload, retain and Last Will tests using an asynchronous fake.
- Event fan-out, SSE framing, stale transitions and recovery-path tests.
- Live Raspberry Pi simulator SSE, authenticated MQTT temperatures and retained service state,
  stale probe availability, absence of retained temperatures, and broker Last Will after forced exit.
- Final Raspberry Pi quality gate: 71 tests, 93.26 per cent coverage, Ruff and strict mypy.

## [0.3.0] - 2026-09-04

### Added

- Versioned FastAPI administrative resources and generated OpenAPI.
- Persistent asynchronous scan and connection operation metadata.
- SQLite persistence for registered devices, desired state and configuration overrides.
- Layered typed configuration with whole-update validation and ETag concurrency.
- Bearer-token authentication, salted scrypt hashing and one-time token rotation responses.
- Write-only MQTT password resource with redacted validation errors.

### Validated

- Simulator-backed API on the target Raspberry Pi: health, asynchronous discovery, device
  registration and connection, four probe readings, and battery state.
- Raspberry Pi quality gate with 58 tests, 93.28 per cent coverage, Ruff and strict mypy.

## [0.2.0] - 2026-09-04

### Added

- Production Weber iGrill V202 adapter behind a shared asynchronous device boundary.
- Scheduled continuous-discovery supervisor with separate missing and connected cadences.
- Explicit desired and observed connection state machine with deterministic backoff tests.
- Four-channel probe presence, availability, timestamps, sequences and source models.
- Deterministic one-to-four-probe simulator with temperature patterns and injected fault states.
- Sanitised physical BLE fixture and a privacy-safe production-adapter validation command.

### Validated

- Production adapter on Raspberry Pi OS with two attached physical probes exactly matching the
  V202 display at 19°C and 21°C, two unattached channels reported absent, and battery at 60 per
  cent.

## [0.1.0] - 2026-09-04

### Added

- Initial v0.1.0 repository scaffold and quality workflow.
- Focused Bleak-based V202 discovery, authentication, probe and battery proof.
- Protocol decoding tests, documentation structure, licence review and provenance record.
- Explicitly bounded Linux connection, GATT service resolution and disconnection in the proof.
- V202 temperature-unit payload handling based on its first byte, retaining trailing bytes as evidence.
- Sanitised per-probe payload diagnostics when no inserted probe can be decoded.
- Three-byte V202 probe framing, decoding the leading 16-bit value and preserving its status byte.
- Raw V202 Celsius decoding based on physical display comparison, without guessing from extended unit metadata.

### Validated

- Physical V202 discovery, pairing, zero-challenge loopback authentication, 20.0°C probe decoding
  against the device display, 60 per cent battery reading and private-address-free output.
