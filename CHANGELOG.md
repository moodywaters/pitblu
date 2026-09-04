# Changelog

All notable changes will be documented here.

## [Unreleased]

### Added

- Production Weber iGrill V202 adapter behind a shared asynchronous device boundary.
- Scheduled continuous-discovery supervisor with separate missing and connected cadences.
- Explicit desired and observed connection state machine with deterministic backoff tests.
- Four-channel probe presence, availability, timestamps, sequences and source models.
- Deterministic one-to-four-probe simulator with temperature patterns and injected fault states.
- Sanitised physical BLE fixture and a privacy-safe production-adapter validation command.

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
