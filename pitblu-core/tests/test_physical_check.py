import asyncio

import pytest

from pitblu_core.adapters.base import AdapterError
from pitblu_core.adapters.simulated import SimulatedIGrillAdapter
from pitblu_core.physical_check import collect_snapshot


def test_collect_snapshot_uses_adapter_boundary_and_safe_output() -> None:
    adapter = SimulatedIGrillAdapter(4)
    result = asyncio.run(collect_snapshot(adapter, scan_duration=1))

    assert result["connectionState"] == "polling"
    assert result["source"] == "simulated"
    assert result["bluetoothAddressIncluded"] is False
    assert len(result["probes"]) == 4
    assert not adapter.is_connected


def test_collect_snapshot_fails_when_no_supported_device_is_visible() -> None:
    adapter = SimulatedIGrillAdapter(1)
    adapter.set_connection_available(False)
    with pytest.raises(AdapterError, match="no supported"):
        asyncio.run(collect_snapshot(adapter, scan_duration=1))
