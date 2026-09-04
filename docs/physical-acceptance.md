# Physical acceptance

Status: pending

## Preconditions

- Target Raspberry Pi environment matches the project plan.
- The iGrill advertises as `iGrill_V202-CD09`.
- At least one probe is inserted and its display value is noted.
- The official Weber application is fully closed.
- No Bluetooth address, LAN address, token or broker secret is captured.

## Procedure

The operator and Codex use one Raspberry Pi command at a time. The repository is transferred or
checked out, an isolated Python 3.13 environment is created, dependencies are installed, tests are
run, and then `pitboss-ble-proof` is executed. Each step waits for the preceding output.

## Pass record

Do not mark this document passed until the output shows:

- `source` equal to `physical`;
- model `igrill-v202`;
- successful zero-challenge loopback authentication;
- a battery percentage from 0 through 100;
- at least one present probe with `temperatureC` matching the display within 1 degree Celsius;
- `bluetoothAddressIncluded` equal to `false`.

Raw payload bytes may be retained as sanitised protocol evidence. Bluetooth addresses must not be
retained. After validation, record the date, target software versions, redacted output and manual
display comparison here.

