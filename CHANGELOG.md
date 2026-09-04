# Changelog

All notable changes will be documented here.

## [Unreleased]

No changes yet.

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
