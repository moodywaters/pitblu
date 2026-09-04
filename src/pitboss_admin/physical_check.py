"""Manual, privacy-safe validation of the production V202 adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from pitboss_admin.adapters.base import AdapterError, DeviceAdapter
from pitboss_admin.adapters.igrill_v202 import BleakIGrillV202Adapter
from pitboss_admin.connection import ConnectionState, ConnectionStateMachine


async def collect_snapshot(
    adapter: DeviceAdapter,
    *,
    scan_duration: float = 5.0,
) -> dict[str, Any]:
    """Discover one supported device and return a safe adapter-level snapshot."""
    machine = ConnectionStateMachine()
    candidates = await adapter.discover(scan_duration)
    if not candidates:
        raise AdapterError("no supported V202 was discovered")

    candidate = candidates[0]
    machine.discovered()
    machine.request_connect()
    machine.transition(ConnectionState.INITIALISING)
    try:
        await adapter.connect(candidate)
        machine.transition(ConnectionState.CONNECTED)
        machine.transition(ConnectionState.POLLING)
        snapshot = await adapter.read_snapshot()
        return {
            "batteryAvailable": snapshot.battery_available,
            "batteryPercent": snapshot.battery_percent,
            "bluetoothAddressIncluded": False,
            "connectionState": machine.observed.value,
            "deviceName": candidate.name,
            "model": snapshot.model,
            "observedAt": snapshot.observed_at.isoformat(),
            "probes": [
                {
                    "available": probe.available,
                    "errorCode": probe.error_code,
                    "observedAt": probe.observed_at.isoformat(),
                    "present": probe.present,
                    "probe": probe.number,
                    "sequence": probe.sequence,
                    "source": probe.source.value,
                    "temperatureC": probe.temperature_c,
                }
                for probe in snapshot.probes
            ],
            "sequence": snapshot.sequence,
            "source": snapshot.source.value,
        }
    finally:
        await adapter.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-duration", type=float, default=5.0)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--initialise-timeout", type=float, default=15.0)
    parser.add_argument("--read-timeout", type=float, default=5.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    adapter = BleakIGrillV202Adapter(
        connect_timeout=args.connect_timeout,
        initialise_timeout=args.initialise_timeout,
        read_timeout=args.read_timeout,
    )
    try:
        result = asyncio.run(collect_snapshot(adapter, scan_duration=args.scan_duration))
    except KeyboardInterrupt:
        print("Physical adapter check interrupted.")
        return 130
    except Exception as exc:
        print(f"Physical adapter check failed: {type(exc).__name__}")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
