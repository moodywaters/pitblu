import asyncio

import pytest

from pitblu_core.adapters.simulated import SimulatedIGrillAdapter
from pitblu_core.discovery import DiscoverySupervisor


def test_scan_once_reports_results_and_uses_cadence() -> None:
    adapter = SimulatedIGrillAdapter(1)
    seen: list[object] = []

    async def on_results(results: object) -> None:
        seen.append(results)
        supervisor.stop()

    supervisor = DiscoverySupervisor(adapter, on_results=on_results)
    results = asyncio.run(supervisor.scan_once())
    assert results == seen[0]
    assert supervisor.next_interval() == 15
    asyncio.run(adapter.connect(results[0]))
    assert supervisor.next_interval() == 60
    asyncio.run(supervisor.run())


def test_run_scans_until_stopped_by_callback() -> None:
    adapter = SimulatedIGrillAdapter(1)
    scans = 0

    async def stop_after_first_scan(_results: object) -> None:
        nonlocal scans
        scans += 1
        running.stop()

    running = DiscoverySupervisor(adapter, on_results=stop_after_first_scan)
    asyncio.run(running.run())
    assert scans == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scan_duration": 0},
        {"missing_interval": 0},
        {"connected_interval": 0},
    ],
)
def test_discovery_rejects_invalid_timing(kwargs: object) -> None:
    with pytest.raises(ValueError):
        DiscoverySupervisor(SimulatedIGrillAdapter(), **kwargs)  # type: ignore[arg-type]
