"""Administrative service used by the REST transport."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine
from time import monotonic
from typing import Literal
from uuid import uuid4

from pitboss_admin.adapters.base import DeviceAdapter
from pitboss_admin.connection import BackoffPolicy, ConnectionState, ConnectionStateMachine
from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import DiscoveredDevice, utc_now
from pitboss_admin.storage import AdministrativeStore
from pitboss_admin.telemetry import TelemetryState


class ResourceNotFoundError(LookupError):
    pass


class StateConflictError(RuntimeError):
    pass


def _device_view(row: dict[str, object]) -> dict[str, object]:
    return {
        "deviceId": row["device_id"],
        "name": row["name"],
        "friendlyName": row["friendly_name"],
        "model": row["model"],
        "automaticReconnection": bool(row["auto_reconnect"]),
        "desiredState": row["desired_state"],
        "observedState": row["observed_state"],
        "createdAt": row["created_at"],
    }


def _operation_view(row: dict[str, object]) -> dict[str, object]:
    return {
        "operationId": row["operation_id"],
        "kind": row["kind"],
        "deviceId": row["device_id"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "errorCode": row["error_code"],
    }


class AdministrationService:
    def __init__(
        self,
        adapter: DeviceAdapter,
        store: AdministrativeStore,
        telemetry: TelemetryState | None = None,
        *,
        poll_interval: float = 5,
        degraded_after: int = 3,
        reconnect_after: float = 30,
        stable_after: float = 60,
        scan_duration: float = 5,
        missing_scan_interval: float = 15,
        connected_scan_interval: float = 60,
        shutdown_timeout: float = 10,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("poll interval must be positive")
        self.adapter = adapter
        self.store = store
        self.telemetry = telemetry or TelemetryState(EventBus())
        self.poll_interval = poll_interval
        self._candidates: dict[str, DiscoveredDevice] = {}
        self._scan_results: dict[str, list[dict[str, object]]] = {}
        self._connected_device: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._polling_tasks: dict[str, asyncio.Task[None]] = {}
        self._recoveries: dict[str, asyncio.Task[None]] = {}
        self._backoffs: dict[str, BackoffPolicy] = {}
        self._active: dict[str, dict[str, object]] = {}
        self._io_lock = asyncio.Lock()
        self._owner: str | None = None
        self._closing = False
        self._sleep = sleep
        self._clock = clock
        self.degraded_after = degraded_after
        self.reconnect_after = reconnect_after
        self.stable_after = stable_after
        self.scan_duration = scan_duration
        self.missing_scan_interval = missing_scan_interval
        self.connected_scan_interval = connected_scan_interval
        self._discovery_task: asyncio.Task[None] | None = None
        self.discovery_error: str | None = None
        self.shutdown_timeout = shutdown_timeout
        self.last_error: str | None = None
        self.last_failure_stage: str | None = None

    async def start(self) -> None:
        self.store.interrupt_operations(utc_now().isoformat())
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        for row in self.store.devices():
            device_id = str(row["device_id"])
            self.store.update_device(device_id, {"observed_state": "disconnected"})
            if (
                row["desired_state"] == "connected"
                and row["auto_reconnect"]
                and self._owner is None
            ):
                self._owner = device_id
                self._schedule_recovery(device_id, immediate=True)

    async def _discovery_loop(self) -> None:
        while not self._closing:
            interval = (
                self.connected_scan_interval
                if self.adapter.is_connected
                else self.missing_scan_interval
            )
            await asyncio.sleep(interval)
            try:
                async with self._io_lock:
                    candidates = await self.adapter.discover(self.scan_duration)
                self._candidates = {item.discovery_id: item for item in candidates}
                self.discovery_error = None
            except Exception:
                self.discovery_error = "bluetooth_scan_failed"

    async def _event(self, operation: dict[str, object]) -> None:
        await self.telemetry.events.publish(
            TelemetryEvent(
                type=EventType.OPERATION,
                sequence=1,
                source=self.adapter.source,
                device_id=str(operation["device_id"]) if operation.get("device_id") else None,
                data={
                    "operationId": operation["operation_id"],
                    "kind": operation["kind"],
                    "status": operation["status"],
                    "errorCode": operation.get("error_code"),
                },
            )
        )

    def _new_operation(self, kind: str, device_id: str | None = None) -> dict[str, object]:
        timestamp = utc_now().isoformat()
        row: dict[str, object] = {
            "operation_id": uuid4().hex,
            "kind": kind,
            "device_id": device_id,
            "status": "queued",
            "created_at": timestamp,
            "updated_at": timestamp,
            "error_code": None,
        }
        self.store.save_operation(row)
        return row

    def _finish(self, row: dict[str, object], error: Exception | None = None) -> dict[str, object]:
        row["status"] = "succeeded" if error is None else "failed"
        row["error_code"] = None if error is None else "device_operation_failed"
        row["updated_at"] = utc_now().isoformat()
        self.store.save_operation(row)
        self._schedule(self._event(row.copy()))
        return _operation_view(row)

    def _schedule(self, coroutine: Coroutine[object, object, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)

        def finished(done: asyncio.Task[None]) -> None:
            self._tasks.discard(done)
            if not done.cancelled() and done.exception() is not None:
                self.last_error = "background_task_failed"
                logging.getLogger(__name__).error('{"event":"background_task_failed"}')

        task.add_done_callback(finished)

    def start_scan(self, duration: float) -> dict[str, object]:
        if self._closing:
            raise StateConflictError("service is stopping")
        for row in self.store.operations():
            if row["kind"] == "scan" and row["status"] in {"queued", "running"}:
                return _operation_view(row)
        operation = self._new_operation("scan")
        self._schedule(self._execute_scan(operation, duration))
        return _operation_view(operation)

    async def _execute_scan(self, operation: dict[str, object], duration: float) -> None:
        operation["status"] = "running"
        operation["updated_at"] = utc_now().isoformat()
        self.store.save_operation(operation)
        try:
            async with self._io_lock:
                candidates = await self.adapter.discover(duration)
            self._candidates = {candidate.discovery_id: candidate for candidate in candidates}
            results: list[dict[str, object]] = [
                {
                    "discoveryId": candidate.discovery_id,
                    "name": candidate.name,
                    "model": candidate.model,
                    "rssi": candidate.rssi,
                }
                for candidate in candidates
            ]
            self._scan_results[str(operation["operation_id"])] = results
            while len(self._scan_results) > 100:
                self._scan_results.pop(next(iter(self._scan_results)))
        except asyncio.CancelledError:
            operation.update(
                {
                    "status": "failed",
                    "error_code": "interrupted",
                    "updated_at": utc_now().isoformat(),
                }
            )
            self.store.save_operation(operation)
            raise
        except Exception as exc:
            self._finish(operation, exc)
            return
        self._finish(operation)

    def scan_result(self, operation_id: str) -> dict[str, object]:
        operation = self.operation(operation_id)
        if operation["kind"] != "scan":
            raise ResourceNotFoundError("scan not found")
        return operation | {"devices": self._scan_results.get(operation_id, [])}

    def register(
        self,
        discovery_id: str,
        friendly_name: str | None,
        automatic_reconnection: bool,
    ) -> dict[str, object]:
        candidate = self._candidates.get(discovery_id)
        if candidate is None:
            raise StateConflictError("discovery result is no longer available")
        if candidate._identity is not None and any(
            row.get("identity") == candidate._identity for row in self.store.devices()
        ):
            raise StateConflictError("device is already registered")
        base = re.sub(r"[^a-z0-9]+", "-", candidate.name.lower()).strip("-")
        device_id = base or f"igrill-{uuid4().hex[:8]}"
        if self.store.device(device_id) is not None:
            raise StateConflictError("device is already registered")
        row: dict[str, object] = {
            "device_id": device_id,
            "discovery_id": discovery_id,
            "name": candidate.name,
            "friendly_name": friendly_name,
            "model": candidate.model,
            "auto_reconnect": automatic_reconnection,
            "desired_state": "disconnected",
            "observed_state": "discovered",
            "created_at": utc_now().isoformat(),
            "identity": candidate._identity,
        }
        self.store.save_device(row)
        return _device_view(row)

    def devices(self) -> list[dict[str, object]]:
        return [_device_view(row) for row in self.store.devices()]

    def device(self, device_id: str) -> dict[str, object]:
        row = self.store.device(device_id)
        if row is None:
            raise ResourceNotFoundError("device not found")
        return _device_view(row)

    def patch_device(
        self,
        device_id: str,
        friendly_name: str | None,
        automatic_reconnection: bool | None,
        discovery_id: str | None = None,
        *,
        update_friendly_name: bool = True,
    ) -> dict[str, object]:
        values: dict[str, object] = {}
        if update_friendly_name:
            values["friendly_name"] = friendly_name
        if discovery_id is not None:
            if self._owner == device_id:
                raise StateConflictError("disconnect before selecting a device identity")
            candidate = self._candidates.get(discovery_id)
            if candidate is None:
                raise StateConflictError("discovery result is no longer available")
            if candidate._identity is not None and any(
                row["device_id"] != device_id and row.get("identity") == candidate._identity
                for row in self.store.devices()
            ):
                raise StateConflictError("device identity is already registered")
            values.update({"identity": candidate._identity, "discovery_id": discovery_id})
        if automatic_reconnection is not None:
            values["auto_reconnect"] = automatic_reconnection
        if values and not self.store.update_device(device_id, values):
            raise ResourceNotFoundError("device not found")
        return self.device(device_id)

    async def delete_device(self, device_id: str) -> None:
        self.device(device_id)
        active = self._active.get(device_id)
        if active and active["status"] in {"queued", "running"}:
            raise StateConflictError("device operation is in progress")
        await self._stop_recovery(device_id)
        if self._connected_device == device_id:
            await self._stop_polling(device_id)
            async with self._io_lock:
                await self.adapter.disconnect()
            self._connected_device = None
        await self.telemetry.remove(device_id)
        self.store.delete_device(device_id)
        if self._owner == device_id:
            self._owner = None

    def start_connection_operation(
        self, device_id: str, action: Literal["connect", "disconnect", "reconnect"]
    ) -> dict[str, object]:
        if self.store.device(device_id) is None:
            raise ResourceNotFoundError("device not found")
        if self._closing:
            raise StateConflictError("service is stopping")
        active = self._active.get(device_id)
        if active and active["status"] in {"queued", "running"}:
            if active["kind"] == action:
                return _operation_view(active)
            raise StateConflictError("device operation is in progress")
        if action != "disconnect":
            if self._owner not in {None, device_id}:
                raise StateConflictError("adapter is owned by another registered device")
            self._owner = device_id
        desired = "disconnected" if action == "disconnect" else "connected"
        self.store.update_device(device_id, {"desired_state": desired})
        operation = self._new_operation(action, device_id)
        self._active[device_id] = operation
        self._schedule(self._execute_connection(operation, device_id, action))
        return _operation_view(operation)

    async def _execute_connection(
        self,
        operation: dict[str, object],
        device_id: str,
        action: Literal["connect", "disconnect", "reconnect"],
        *,
        recovering: bool = False,
    ) -> None:
        operation["status"] = "running"
        operation["updated_at"] = utc_now().isoformat()
        self.store.save_operation(operation)
        row = self.store.device(device_id)
        if row is None:
            self._finish(operation, ResourceNotFoundError("device not found"))
            return
        stage = "prepare"
        try:
            if not recovering:
                await self._stop_recovery(device_id)
            if action == "disconnect":
                stage = "disconnect"
                await self._stop_polling(device_id)
                if self._owner in {None, device_id}:
                    async with self._io_lock:
                        await self.adapter.disconnect()
                    self._connected_device = None
                    self._owner = None
                await self.telemetry.connection(device_id, "disconnected")
                self.store.update_device(
                    device_id,
                    {"desired_state": "disconnected", "observed_state": "disconnected"},
                )
            else:
                if (
                    action == "connect"
                    and self._connected_device == device_id
                    and self.adapter.is_connected
                ):
                    self._finish(operation)
                    return
                if action == "reconnect":
                    await self._stop_polling(device_id)
                    async with self._io_lock:
                        await self.adapter.disconnect()
                # Discovery replaces the adapter's candidate cache. Keep resolution and
                # connection atomic so background scans cannot invalidate the selection.
                async with self._io_lock:
                    stage = "discovery"
                    candidate = self._candidates.get(str(row["discovery_id"]))
                    if candidate is None:
                        candidates = await self.adapter.discover(self.scan_duration)
                        self._candidates = {item.discovery_id: item for item in candidates}
                        identity = row.get("identity")
                        if identity is not None:
                            candidate = next(
                                (item for item in candidates if item._identity == identity), None
                            )
                        if candidate is None and isinstance(identity, str):
                            stage = "bluez_release"
                            released = await self.adapter.recover_registered(identity)
                            if released:
                                stage = "rediscovery"
                                candidates = await self.adapter.discover(self.scan_duration)
                                self._candidates = {item.discovery_id: item for item in candidates}
                                candidate = next(
                                    (item for item in candidates if item._identity == identity),
                                    None,
                                )
                        if candidate is None:
                            stage = "registered_identity_missing"
                            raise StateConflictError(
                                "registered identity not found; legacy registrations require "
                                "a fresh scan and explicit selection"
                            )
                        self.store.update_device(
                            device_id, {"discovery_id": candidate.discovery_id}
                        )
                    machine = ConnectionStateMachine()
                    machine.discovered()
                    machine.request_connect(force=action == "reconnect")
                    machine.transition(ConnectionState.INITIALISING)
                    stage = "connect_initialise"
                    await self.adapter.connect(candidate)
                    machine.transition(ConnectionState.CONNECTED)
                    machine.transition(ConnectionState.POLLING)
                    stage = "initial_read"
                    snapshot = await self.adapter.read_snapshot()
                stage = "record_snapshot"
                await self.telemetry.record(device_id, snapshot)
                self._connected_device = device_id
                self.last_error = None
                self.last_failure_stage = None
                self._start_polling(device_id)
                self.store.update_device(
                    device_id,
                    {"desired_state": "connected", "observed_state": machine.observed.value},
                )
        except asyncio.CancelledError:
            operation.update(
                {
                    "status": "failed",
                    "error_code": "interrupted",
                    "updated_at": utc_now().isoformat(),
                }
            )
            self.store.save_operation(operation)
            raise
        except Exception as exc:
            self.last_error = "device_operation_failed"
            self.last_failure_stage = stage
            logging.getLogger(__name__).warning(
                json.dumps(
                    {"event": "device_operation_failed", "deviceId": device_id, "stage": stage}
                )
            )
            observed = "disconnected" if action == "disconnect" else "backoff"
            self.store.update_device(device_id, {"observed_state": observed})
            self._finish(operation, exc)
            if action != "disconnect" and not recovering:
                self._schedule_recovery(device_id)
            return
        self._finish(operation)

    async def close(self) -> None:
        self._closing = True
        if self._discovery_task is not None:
            self._discovery_task.cancel()
            await asyncio.gather(self._discovery_task, return_exceptions=True)
        operations = tuple(self._tasks)
        for task in operations:
            task.cancel()
        if operations:
            await asyncio.gather(*operations, return_exceptions=True)
        recovery = tuple(self._recoveries.values())
        self._recoveries.clear()
        for task in recovery:
            task.cancel()
        if recovery:
            await asyncio.gather(*recovery, return_exceptions=True)
        polling = tuple(self._polling_tasks.values())
        self._polling_tasks.clear()
        for task in polling:
            task.cancel()
        if polling:
            await asyncio.gather(*polling, return_exceptions=True)
        if self._tasks:
            for task in tuple(self._tasks):
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self.store.interrupt_operations(utc_now().isoformat())
        if self._connected_device is not None:
            await self.telemetry.connection(self._connected_device, "disconnected")
            self.store.update_device(self._connected_device, {"observed_state": "disconnected"})
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.adapter.disconnect(), timeout=self.shutdown_timeout)
        await self.telemetry.close()

    async def _stop_recovery(self, device_id: str) -> None:
        task = self._recoveries.pop(device_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _schedule_recovery(self, device_id: str, *, immediate: bool = False) -> None:
        row = self.store.device(device_id)
        if (
            self._closing
            or not row
            or not row["auto_reconnect"]
            or row["desired_state"] != "connected"
        ):
            return
        if device_id in self._recoveries:
            return
        task = asyncio.create_task(self._recover(device_id, immediate))
        self._recoveries[device_id] = task

        def discard(done: asyncio.Task[None]) -> None:
            if self._recoveries.get(device_id) is done:
                self._recoveries.pop(device_id, None)

        task.add_done_callback(discard)

    async def _recover(self, device_id: str, immediate: bool) -> None:
        backoff = self._backoffs.setdefault(device_id, BackoffPolicy())
        while not self._closing:
            row = self.store.device(device_id)
            if not row or row["desired_state"] != "connected" or not row["auto_reconnect"]:
                return
            if not immediate:
                await self._sleep(backoff.next_delay())
            immediate = False
            operation = self._new_operation("reconnect", device_id)
            await self._execute_connection(operation, device_id, "reconnect", recovering=True)
            if operation["status"] == "succeeded":
                return

    def _start_polling(self, device_id: str) -> None:
        previous = self._polling_tasks.pop(device_id, None)
        if previous is not None:
            previous.cancel()
        task = asyncio.create_task(self._poll(device_id))
        self._polling_tasks[device_id] = task

        def discard(completed: asyncio.Task[None]) -> None:
            if self._polling_tasks.get(device_id) is completed:
                self._polling_tasks.pop(device_id, None)
            if not completed.cancelled() and completed.exception() is not None:
                self.last_error = "polling_task_failed"
                self._schedule_recovery(device_id)

        task.add_done_callback(discard)

    async def _stop_polling(self, device_id: str) -> None:
        task = self._polling_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _poll(self, device_id: str) -> None:
        failures = 0
        last_valid = self._clock()
        stable_since = last_valid
        last_observed = self.telemetry.observed_at(device_id)
        while self._connected_device == device_id:
            await self._sleep(self.poll_interval)
            if self._connected_device != device_id:
                return
            try:
                async with self._io_lock:
                    snapshot = await self.adapter.read_snapshot()
            except Exception:
                failures += 1
            else:
                await self.telemetry.record(device_id, snapshot)
                fresh = (
                    utc_now() - snapshot.observed_at
                ).total_seconds() < self.telemetry.stale_after.total_seconds()
                if (
                    fresh
                    and any(probe.available for probe in snapshot.probes)
                    and (last_observed is None or snapshot.observed_at > last_observed)
                ):
                    last_observed = snapshot.observed_at
                    failures = 0
                    last_valid = self._clock()
                    self.store.update_device(device_id, {"observed_state": "polling"})
                    if self._clock() - stable_since >= self.stable_after:
                        self._backoffs.setdefault(device_id, BackoffPolicy()).reset()
                else:
                    failures += 1
            if failures:
                stable_since = self._clock()
                if failures >= self.degraded_after:
                    self.store.update_device(device_id, {"observed_state": "degraded"})
                    await self.telemetry.connection(device_id, "degraded")
            if not self.adapter.is_connected or self._clock() - last_valid >= self.reconnect_after:
                self.last_error = "device_read_failed"
                self.store.update_device(device_id, {"observed_state": "backoff"})
                await self.telemetry.connection(device_id, "backoff")
                self._schedule_recovery(device_id)
                return

    def diagnostics(self) -> dict[str, object]:
        return {
            "stopping": self._closing,
            "connected": self.adapter.is_connected,
            "pollingTasks": len(self._polling_tasks),
            "recoveryTasks": len(self._recoveries),
            "pendingOperations": len(self._tasks),
            "errorCode": self.last_error,
            "failureStage": self.last_failure_stage,
            "discoveryErrorCode": self.discovery_error,
        }

    def probes(self, device_id: str) -> list[dict[str, object]]:
        self.device(device_id)
        return self.telemetry.probes(device_id)

    def battery(self, device_id: str) -> dict[str, object] | None:
        self.device(device_id)
        return self.telemetry.battery(device_id)

    def operations(self) -> list[dict[str, object]]:
        return [_operation_view(row) for row in self.store.operations()]

    def operation(self, operation_id: str) -> dict[str, object]:
        row = self.store.operation(operation_id)
        if row is None:
            raise ResourceNotFoundError("operation not found")
        return _operation_view(row)
