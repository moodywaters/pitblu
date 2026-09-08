import asyncio

import pytest

from pitblu_core.adapters.simulated import SimulatedIGrillAdapter
from pitblu_core.events import EventBus, EventType
from pitblu_core.service import AdministrationService
from pitblu_core.storage import AdministrativeStore
from pitblu_core.telemetry import TelemetryState


def test_service_polling_records_a_subsequent_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        adapter = SimulatedIGrillAdapter()
        candidate = (await adapter.discover(1))[0]
        await adapter.connect(candidate)
        bus = EventBus()
        telemetry = TelemetryState(bus)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store, telemetry)
        service._connected_device = "device-1"
        original_read = adapter.read_snapshot

        async def no_wait(_delay: float) -> None:
            return None

        async def one_read():  # type: ignore[no-untyped-def]
            result = await original_read()
            service._connected_device = None
            return result

        monkeypatch.setattr("pitblu_core.service.asyncio.sleep", no_wait)
        service._sleep = no_wait
        monkeypatch.setattr(adapter, "read_snapshot", one_read)
        await service._poll("device-1")

        temperatures = [item for item in bus.recent() if item.type is EventType.PROBE_TEMPERATURE]
        assert len(temperatures) == 4
        assert temperatures[0].data == {"temperatureC": 20.0}
        await service.close()
        store.close()

    asyncio.run(exercise())


def test_service_polling_stops_cleanly_after_read_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        adapter = SimulatedIGrillAdapter()
        service = AdministrationService(adapter, AdministrativeStore())
        service._connected_device = "device-1"

        async def no_wait(_delay: float) -> None:
            return None

        monkeypatch.setattr("pitblu_core.service.asyncio.sleep", no_wait)
        service._sleep = no_wait
        await service._poll("device-1")
        assert service.telemetry.probes("device-1") == []
        await service.close()
        service.store.close()

    asyncio.run(exercise())


def test_service_rejects_non_positive_poll_interval() -> None:
    store = AdministrativeStore()
    try:
        with pytest.raises(ValueError, match="positive"):
            AdministrationService(SimulatedIGrillAdapter(), store, poll_interval=0)
    finally:
        store.close()
