# Bluetooth protocol notes

## v0.1.0 hypothesis

The V202 is identified by temperature service UUID
`ada7590f-2e6d-469e-8f7b-1822b386a5e9`. The proof writes sixteen zero bytes to application
challenge characteristic `64ac0002-4a4b-4b58-9f37-94d3c52ffdf7`, reads the 16-byte encrypted
device challenge from `64ac0003-4a4b-4b58-9f37-94d3c52ffdf7`, and writes that value unchanged to
device response `64ac0004-4a4b-4b58-9f37-94d3c52ffdf7`.

Probe characteristics are `06ef0002`, `06ef0004`, `06ef0006` and `06ef0008` under the Weber UUID
suffix `2e06-4b79-9e33-fce2c42805ec`. Values are unsigned 16-bit little-endian integers. Value
63536 indicates an unplugged probe. The first byte of characteristic `06ef0001` reports 0 for
Fahrenheit or 1 for Celsius. The V202 may return trailing bytes, which are retained as sanitised
evidence but do not alter the unit. The proof normalises a Fahrenheit-configured display value to Celsius. Battery level uses
the standard Bluetooth characteristic `00002a19-0000-1000-8000-00805f9b34fb` and is a single
percentage byte.

These are research hypotheses until the target hardware evidence is recorded. The proof reads but
does not change the device's unit or other configuration.

The Bleak client requests pairing and wraps connection plus GATT service resolution in an explicit
asyncio deadline. This outer deadline is required because the backend's constructor timeout did not
bound service resolution during the first physical trial.

If no probe can be decoded, the proof reports each read's exception type or sanitised raw payload
length and hex value. This diagnostic contains protocol bytes only and never a Bluetooth address.

## Privacy

The advertised name is not treated as the Bluetooth address. Conventional colon-separated
addresses are redacted from diagnostic errors and are never included in the success document.
