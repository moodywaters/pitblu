# Bluetooth protocol notes

Released v0.6.0 protocol and adapter behaviour. Dated supporting evidence is kept
in [historical acceptance](history/acceptance-evidence.md).

## Confirmed protocol and remaining uncertainty

The V202 is identified by temperature service UUID
`ada7590f-2e6d-469e-8f7b-1822b386a5e9`. The proof writes sixteen zero bytes to application
challenge characteristic `64ac0002-4a4b-4b58-9f37-94d3c52ffdf7`, reads the 16-byte encrypted
device challenge from `64ac0003-4a4b-4b58-9f37-94d3c52ffdf7`, and writes that value unchanged to
device response `64ac0004-4a4b-4b58-9f37-94d3c52ffdf7`.

Probe characteristics are `06ef0002`, `06ef0004`, `06ef0006` and `06ef0008` under the Weber UUID
suffix `2e06-4b79-9e33-fce2c42805ec`. The first two bytes are an unsigned 16-bit little-endian
temperature in Celsius. The physical V202 returned a third `0x80` status byte, which is preserved
as evidence but is not part of the numeric value. Value 63536 indicates an unplugged probe.

Older references describe characteristic `06ef0001` as a one-byte display-unit flag with 0 for
Fahrenheit and 1 for Celsius. The target V202 instead returned `000a000002`, so the spike labels the
unit metadata as undetermined and does not use it to transform the raw temperature. Direct evidence
showed raw probe value `1400` and a simultaneous display value of 20°C. Battery level uses
the standard Bluetooth characteristic `00002a19-0000-1000-8000-00805f9b34fb` and is a single
percentage byte.

The service UUID and initialisation sequence were physically confirmed. The three-byte
probe framing and raw Celsius interpretation were observed
directly on the target V202 on 4 September 2026. The proof reads but does not change the device's
unit or other configuration.

## Supporting physical observations

Physical acceptance confirmed the V202 service UUID and zero-challenge loopback sequence. The
standard battery characteristic returned `3c`, or 60 per cent. An inserted 20°C probe returned
`140080`; unplugged channels returned `30f880`, whose leading `30f8` is the little-endian 63536
sentinel. The V202 returned `000a000002` from `06ef0001`, not a one-byte display-unit flag.

Two inserted probes appeared correctly on the first and second logical temperature characteristics,
both at the displayed 20°C. The third and fourth characteristics returned the unplugged sentinel.
The production adapter reads all four logical channels. Inserting probes into all four
physical sockets remains part of the complete v1.0.0 physical acceptance suite.

## Production adapter

The production adapter uses the confirmed V202 service and challenge sequence, reads all four
logical probe characteristics on every snapshot and interprets the confirmed unplugged sentinel as
`present: false`. A malformed or failed channel read is isolated to that probe as unavailable, so
one faulty characteristic does not discard other valid readings. Battery failure is represented
independently from probe availability.

Discovery accepts the expected V202 advertised-name prefix or the confirmed temperature service.
It exposes only a process-local opaque discovery identifier. Native BLE objects and Bluetooth
addresses do not appear in model representations or validation output.

Default deadlines follow the project plan: 10 seconds for connection and service resolution, 15
seconds for authentication, and 5 seconds for each GATT read. The physical validation command can
raise the connection allowance explicitly when diagnosing a slow BlueZ service-resolution path.

The Bleak client requests pairing and wraps connection plus GATT service resolution in an explicit
asyncio deadline. This outer deadline is required because the backend's constructor timeout did not
bound service resolution during the first physical trial.

If no probe can be decoded, the proof reports each read's exception type or sanitised raw payload
length and hex value. This diagnostic contains protocol bytes only and never a Bluetooth address.

## Privacy

The advertised name is not treated as the Bluetooth address. Conventional colon-separated
addresses are redacted from diagnostic errors and are never included in the success document.
