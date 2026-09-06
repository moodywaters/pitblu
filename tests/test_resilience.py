import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pitboss_admin.adapters.simulated import SimulatedIGrillAdapter
from pitboss_admin.api import create_app
from pitboss_admin.configuration import ConfigurationManager
from pitboss_admin.connection import BackoffPolicy
from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import DeviceSnapshot, DiscoveredDevice, TelemetrySource, utc_now
from pitboss_admin.mqtt import MqttPublisher, MqttSettings
from pitboss_admin.service import AdministrationService, StateConflictError
from pitboss_admin.storage import AdministrativeStore


async def until(predicate: Callable[[], bool]) -> None:
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("task did not reach expected state")


async def register(service: AdministrationService) -> str:
    operation = service.start_scan(1)
    await until(lambda: service.operation(str(operation["operationId"]))["status"] == "succeeded")
    candidate = next(iter(service._candidates))
    return str(service.register(candidate, None, True)["deviceId"])


async def command(service: AdministrationService, device_id: str) -> None:
    operation = service.start_connection_operation(device_id, "connect")
    await until(lambda: service.operation(str(operation["operationId"]))["status"] == "succeeded")


def test_scan_cannot_invalidate_recovery_candidate_before_connect() -> None:
    class RacingAdapter(SimulatedIGrillAdapter):
        scans = 0
        race = False
        service: AdministrationService

        async def discover(self, duration: float) -> tuple[DiscoveredDevice, ...]:
            self.scans += 1
            self._candidate = replace(self._candidate, discovery_id=str(self.scans))
            if self.race:
                self.race = False
                self.service.start_scan(1)
                await asyncio.sleep(0)
            return await super().discover(duration)

    async def exercise() -> None:
        adapter = RacingAdapter(clock=utc_now)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store)
        adapter.service = service
        try:
            device_id = await register(service)
            service._candidates.clear()
            adapter.race = True
            await command(service, device_id)
            assert service.last_error is None
            assert service.diagnostics()["failureStage"] is None
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_restart_releases_only_registered_leftover_connection() -> None:
    class LeftoverAdapter(SimulatedIGrillAdapter):
        stuck = True
        recovered: list[str]

        def __init__(self) -> None:
            super().__init__(clock=utc_now)
            self.recovered = []

        async def discover(self, duration: float) -> tuple[DiscoveredDevice, ...]:
            return () if self.stuck else await super().discover(duration)

        async def recover_registered(self, identity: str) -> bool:
            self.recovered.append(identity)
            assert identity == "simulated-igrill-v202"
            self.stuck = False
            return True

    async def exercise() -> None:
        store = AdministrativeStore()
        original = AdministrationService(SimulatedIGrillAdapter(clock=utc_now), store)
        device_id = await register(original)
        await command(original, device_id)
        await original.close()
        adapter = LeftoverAdapter()
        restarted = AdministrationService(adapter, store)
        try:
            await restarted.start()
            await until(lambda: restarted._connected_device == device_id)
            assert adapter.recovered == ["simulated-igrill-v202"]
            assert restarted.probes(device_id)[0]["fresh"] is True
        finally:
            await restarted.close()
            store.close()

    asyncio.run(exercise())


def test_restart_restores_only_registered_identity_and_desired_state(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "state.sqlite3"
        store = AdministrativeStore(path)
        first = AdministrationService(SimulatedIGrillAdapter(clock=utc_now), store)
        device_id = await register(first)
        await command(first, device_id)
        await first.close()
        assert store.device(device_id)["desired_state"] == "connected"  # type: ignore[index]
        store.close()

        store = AdministrativeStore(path)
        second = AdministrationService(SimulatedIGrillAdapter(clock=utc_now), store)
        try:
            await second.start()
            await until(lambda: second._connected_device == device_id)
            assert second.probes(device_id)[0]["fresh"] is True
            assert "identity" not in second.device(device_id)
            operation = second.start_connection_operation(device_id, "disconnect")
            await until(
                lambda: second.operation(str(operation["operationId"]))["status"] == "succeeded"
            )
            assert not second._recoveries
            assert not second.adapter.is_connected
        finally:
            await second.close()
            store.close()

    asyncio.run(exercise())


def test_duplicate_commands_and_other_device_ownership_are_safe() -> None:
    async def exercise() -> None:
        store = AdministrativeStore()
        service = AdministrationService(SimulatedIGrillAdapter(clock=utc_now), store)
        try:
            device_id = await register(service)
            first = service.start_connection_operation(device_id, "connect")
            second = service.start_connection_operation(device_id, "connect")
            assert first["operationId"] == second["operationId"]
            with pytest.raises(StateConflictError):
                service.start_connection_operation(device_id, "reconnect")
            with pytest.raises(StateConflictError):
                await service.delete_device(device_id)
            await until(lambda: service._connected_device is not None)
            await command(service, device_id)
            row = dict(store.device(device_id) or {})
            row["device_id"] = "another-device"
            store.save_device(row)
            with pytest.raises(StateConflictError, match="owned"):
                service.start_connection_operation("another-device", "connect")
            operation = service.start_connection_operation("another-device", "disconnect")
            await until(
                lambda: service.operation(str(operation["operationId"]))["status"] == "succeeded"
            )
            assert service.adapter.is_connected
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_failed_connection_retries_and_disconnect_cancels_backoff() -> None:
    async def exercise() -> None:
        delays: list[float] = []
        pause = asyncio.Event()

        async def sleep(delay: float) -> None:
            delays.append(delay)
            await pause.wait()

        adapter = SimulatedIGrillAdapter(clock=utc_now)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store, sleep=sleep)
        try:
            device_id = await register(service)
            adapter.set_connection_available(False)
            service.start_connection_operation(device_id, "connect")
            await until(lambda: bool(delays))
            assert service.device(device_id)["observedState"] == "backoff"
            assert 1.6 <= delays[0] <= 2.4
            adapter.set_connection_available(True)
            operation = service.start_connection_operation(device_id, "reconnect")
            await until(
                lambda: service.operation(str(operation["operationId"]))["status"] == "succeeded"
            )
            assert service.adapter.is_connected
            operation = service.start_connection_operation(device_id, "disconnect")
            await until(
                lambda: service.operation(str(operation["operationId"]))["status"] == "succeeded"
            )
            assert not service._recoveries
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_legacy_identity_is_not_guessed_from_name() -> None:
    async def exercise() -> None:
        store = AdministrativeStore()
        service = AdministrationService(SimulatedIGrillAdapter(clock=utc_now), store)
        try:
            device_id = await register(service)
            store.update_device(
                device_id, {"identity": None, "discovery_id": "old", "auto_reconnect": False}
            )
            service._candidates.clear()
            operation = service.start_connection_operation(device_id, "connect")
            await until(
                lambda: service.operation(str(operation["operationId"]))["status"] == "failed"
            )
            assert not service.adapter.is_connected
            disconnect = service.start_connection_operation(device_id, "disconnect")
            await until(
                lambda: service.operation(str(disconnect["operationId"]))["status"] == "succeeded"
            )
            service.patch_device(device_id, None, True, next(iter(service._candidates)))
            await command(service, device_id)
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_bounded_operational_history_and_interrupted_operations(tmp_path: Path) -> None:
    store = AdministrativeStore(tmp_path / "state.sqlite3")
    for sequence in range(120):
        store.append_event({"sequence": sequence, "type": "operation.state"})
    assert len(store.recent_events()) == 100
    assert store.recent_events()[0]["sequence"] == 20
    store.save_operation(
        {
            "operation_id": "pending",
            "kind": "connect",
            "status": "running",
            "created_at": "now",
            "updated_at": "now",
        }
    )
    store.interrupt_operations("later")
    assert store.operation("pending")["error_code"] == "interrupted"  # type: ignore[index]
    store.close()


def test_mqtt_failure_retries_redacts_error_and_replays_only_retained_state() -> None:
    async def exercise() -> None:
        deliveries: list[tuple[str, str]] = []
        delays: list[float] = []
        attempts = 0
        ready = asyncio.Event()

        class Client:
            async def __aenter__(self) -> "Client":
                return self

            async def __aexit__(self, *_args: object) -> None:
                pass

            async def publish(self, topic: str, payload: str, **_kwargs: Any) -> None:
                deliveries.append((topic, payload))
                if topic.endswith("battery"):
                    ready.set()

        def factory(*_args: Any, **_kwargs: Any) -> Client:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("secret-must-not-appear")
            return Client()

        async def sleep(delay: float) -> None:
            delays.append(delay)

        bus = EventBus()
        for event_type in (EventType.BATTERY, EventType.PROBE_TEMPERATURE):
            await bus.publish(
                TelemetryEvent(
                    type=event_type,
                    sequence=1,
                    source=TelemetrySource.SIMULATED,
                    device_id="test",
                    probe=1,
                    data={"percentage": 50}
                    if event_type is EventType.BATTERY
                    else {"temperatureC": 20},
                )
            )
        publisher = MqttPublisher(
            MqttSettings(),
            client_factory=factory,
            sleep=sleep,
            backoff=BackoffPolicy(jitter_fraction=0),
        )
        task = asyncio.create_task(publisher.run(bus))
        await until(ready.is_set)
        assert delays == [2]
        assert publisher.status()["state"] == "connected"
        assert publisher.status()["failures"] == 1
        assert "secret-must-not-appear" not in str(publisher.status())
        assert not any(topic.endswith("temperature") for topic, _ in deliveries)
        assert bus.session_id in deliveries[-1][1]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert publisher.state == "stopped"

    asyncio.run(exercise())


def test_old_snapshot_does_not_republish_fresh_temperatures() -> None:
    async def exercise() -> None:
        adapter = SimulatedIGrillAdapter(clock=utc_now)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store)
        try:
            device_id = await register(service)
            await command(service, device_id)
            adapter.set_stale(True)
            snapshot = await adapter.read_snapshot()
            bus = service.telemetry.events
            count = len(bus.recent())
            await service.telemetry.record(device_id, snapshot)
            assert len(bus.recent()) == count
            await service.telemetry.mark_stale(snapshot.observed_at + timedelta(seconds=16))
            battery = [item for item in bus.recent() if item.type is EventType.BATTERY][-1]
            assert battery.data["percentage"] is None
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_transient_reads_degrade_then_recover_without_disconnect() -> None:
    async def exercise() -> None:
        ticks = 0.0
        now = utc_now()
        adapter = SimulatedIGrillAdapter(clock=lambda: now + timedelta(seconds=ticks))
        store = AdministrativeStore()
        service = AdministrationService(adapter, store, clock=lambda: ticks, stable_after=5)
        device_id = await register(service)
        await command(service, device_id)
        await service._stop_polling(device_id)
        original = adapter.read_snapshot
        observed: list[str] = []
        reads = 0

        async def sleep(delay: float) -> None:
            nonlocal ticks
            ticks += delay

        async def read() -> DeviceSnapshot:
            nonlocal reads
            reads += 1
            observed.append(str(service.device(device_id)["observedState"]))
            if reads <= 3:
                raise RuntimeError("private failure details")
            if reads == 5:
                service._connected_device = None
            return await original()

        adapter.read_snapshot = read  # type: ignore[method-assign]
        service._sleep = sleep
        try:
            await service._poll(device_id)
            assert reads == 5
            assert "degraded" in observed
            assert adapter.is_connected
            assert service.device(device_id)["observedState"] == "polling"
            assert service._backoffs[device_id].attempt == 0
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_no_valid_reading_deadline_schedules_recovery() -> None:
    async def exercise() -> None:
        ticks = 0.0
        adapter = SimulatedIGrillAdapter(clock=utc_now)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store, clock=lambda: ticks, reconnect_after=15)
        device_id = await register(service)
        await command(service, device_id)
        await service._stop_polling(device_id)

        async def sleep(delay: float) -> None:
            nonlocal ticks
            ticks += delay

        async def fail() -> DeviceSnapshot:
            raise RuntimeError("private details")

        service._sleep = sleep
        adapter.read_snapshot = fail  # type: ignore[method-assign]
        try:
            await service._poll(device_id)
            assert ticks == 15
            assert device_id in service._recoveries
            assert service.diagnostics()["errorCode"] == "device_read_failed"
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())


def test_shutdown_cancels_inflight_scan_and_rejects_new_commands() -> None:
    async def exercise() -> None:
        entered = asyncio.Event()
        adapter = SimulatedIGrillAdapter()
        original = adapter.discover

        async def scan(duration: float):  # type: ignore[no-untyped-def]
            entered.set()
            await asyncio.Event().wait()
            return await original(duration)

        adapter.discover = scan  # type: ignore[method-assign]
        store = AdministrativeStore()
        service = AdministrationService(adapter, store)
        op = service.start_scan(1)
        assert service.start_scan(1)["operationId"] == op["operationId"]
        await until(entered.is_set)
        await service.close()
        assert service.operation(str(op["operationId"]))["errorCode"] == "interrupted"
        assert not service._tasks
        with pytest.raises(StateConflictError, match="stopping"):
            service.start_scan(1)
        store.close()

    asyncio.run(exercise())


def test_mqtt_failure_is_visible_without_secrets_and_shutdown_cancels_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped: list[bool] = []

    class Publisher:
        state = "backoff"

        def __init__(self, *_args: Any) -> None:
            pass

        def status(self) -> dict[str, object]:
            return {"state": self.state, "errorCode": "mqtt_connection_failed"}

        async def run(self, _events: EventBus) -> None:
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)

    monkeypatch.setattr("pitboss_admin.api.MqttPublisher", Publisher)
    store = AdministrativeStore()
    config = ConfigurationManager(store, environ={"PITBOSS_MQTT__ENABLED": "true"})
    with TestClient(
        create_app(adapter=SimulatedIGrillAdapter(), store=store, configuration=config)
    ) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").status_code == 503
        status = client.get("/api/v1/status").json()
        assert status["status"] == "degraded"
        assert status["mqtt"]["errorCode"] == "mqtt_connection_failed"
        assert "password" not in str(status)
    assert stopped == [True]
    store.close()


def test_graceful_mqtt_exit_flushes_offline_state() -> None:
    async def exercise() -> None:
        publications: list[tuple[str, str]] = []
        ready = asyncio.Event()

        class Client:
            async def __aenter__(self) -> "Client":
                return self

            async def __aexit__(self, *_args: object) -> None:
                pass

            async def publish(self, topic: str, payload: str, **_kwargs: Any) -> None:
                publications.append((topic, payload))
                ready.set()

        publisher = MqttPublisher(MqttSettings(), client_factory=lambda *_args, **_kw: Client())
        events = EventBus()
        task = asyncio.create_task(publisher.run(events))
        await until(ready.is_set)
        await events.publish(
            TelemetryEvent(
                type=EventType.BATTERY,
                sequence=2,
                device_id="test",
                source=TelemetrySource.SIMULATED,
                data={"available": False, "percentage": None},
            )
        )
        await events.publish(
            TelemetryEvent(
                type=EventType.SERVICE_AVAILABILITY,
                sequence=2,
                source=TelemetrySource.SIMULATED,
                data={"available": False},
            )
        )
        await until(task.done)
        await task
        assert publisher.state == "stopped"
        assert any(
            topic.endswith("battery") and '"available":false' in payload
            for topic, payload in publications
        )
        assert publications[-1][0].endswith("service/availability")
        assert '"available":false' in publications[-1][1]

    asyncio.run(exercise())


def test_automatic_recovery_succeeds_without_another_rest_command() -> None:
    async def exercise() -> None:
        waiting = asyncio.Event()
        resume = asyncio.Event()

        async def sleep(_delay: float) -> None:
            waiting.set()
            await resume.wait()
            await asyncio.sleep(0)

        adapter = SimulatedIGrillAdapter(clock=utc_now)
        store = AdministrativeStore()
        service = AdministrationService(adapter, store, sleep=sleep)
        try:
            device_id = await register(service)
            adapter.set_connection_available(False)
            operation = service.start_connection_operation(device_id, "connect")
            await until(waiting.is_set)
            assert service.operation(str(operation["operationId"]))["status"] == "failed"
            adapter.set_connection_available(True)
            resume.set()
            await until(lambda: service._connected_device == device_id)
            assert service.probes(device_id)[0]["fresh"] is True
        finally:
            await service.close()
            store.close()

    asyncio.run(exercise())
