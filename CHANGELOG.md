# Changelog

All notable changes will be documented here.

## [Unreleased]

### Added

- Initial v0.1.0 repository scaffold and quality workflow.
- Focused Bleak-based V202 discovery, authentication, probe and battery proof.
- Protocol decoding tests, documentation structure, licence review and provenance record.
- Explicitly bounded Linux connection, GATT service resolution and disconnection in the proof.
- V202 temperature-unit payload handling based on its first byte, retaining trailing bytes as evidence.
- Sanitised per-probe payload diagnostics when no inserted probe can be decoded.
- Three-byte V202 probe framing, decoding the leading 16-bit value and preserving its status byte.
- Raw V202 Celsius decoding based on physical display comparison, without guessing from extended unit metadata.

### Blocked

- v0.1.0 release pending successful physical probe and battery evidence from the target Raspberry Pi.
