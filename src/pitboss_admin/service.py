"""Administrative service used by the REST transport."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Coroutine
from typing import Literal
from uuid import uuid4

from pitboss_admin.adapters.base import DeviceAdapter
from pitboss_admin.connection import ConnectionState, ConnectionStateMachine
from pitboss_admin.events import EventBus
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
        row["error_code"] = None if error is None else type(error).__name__
        row["updated_at"] = utc_now().isoformat()
        self.store.save_operation(row)
        return _operation_view(row)

    def _schedule(self, coroutine: Coroutine[object, object, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def start_scan(self, duration: float) -> dict[str, object]:
        operation = self._new_operation("scan")
        self._schedule(self._execute_scan(operation, duration))
        return _operation_view(operation)

    async def _execute_scan(self, operation: dict[str, object], duration: float) -> None:
        operation["status"] = "running"
        operation["updated_at"] = utc_now().isoformat()
        self.store.save_operation(operation)
        try:
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
    ) -> dict[str, object]:
        values: dict[str, object] = {"friendly_name": friendly_name}
        if automatic_reconnection is not None:
            values["auto_reconnect"] = automatic_reconnection
        if not self.store.update_device(device_id, values):
            raise ResourceNotFoundError("device not found")
        return self.device(device_id)

    async def delete_device(self, device_id: str) -> None:
        self.device(device_id)
        if self._connected_device == device_id:
            await self._stop_polling(device_id)
            await self.adapter.disconnect()
            self._connected_device = None
        await self.telemetry.remove(device_id)
        self.store.delete_device(device_id)

    def start_connection_operation(
        self, device_id: str, action: Literal["connect", "disconnect", "reconnect"]
    ) -> dict[str, object]:
        if self.store.device(device_id) is None:
            raise ResourceNotFoundError("device not found")
        desired = "disconnected" if action == "disconnect" else "connected"
        self.store.update_device(device_id, {"desired_state": desired})
        operation = self._new_operation(action, device_id)
        self._schedule(self._execute_connection(operation, device_id, action))
        return _operation_view(operation)

    async def _execute_connection(
        self,
        operation: dict[str, object],
        device_id: str,
        action: Literal["connect", "disconnect", "reconnect"],
    ) -> None:
        operation["status"] = "running"
        operation["updated_at"] = utc_now().isoformat()
        self.store.save_operation(operation)
        row = self.store.device(device_id)
        if row is None:
            self._finish(operation, ResourceNotFoundError("device not found"))
            return
        try:
            if action == "disconnect":
                await self._stop_polling(device_id)
                await self.adapter.disconnect()
                self._connected_device = None
                await self.telemetry.connection(device_id, "disconnected")
                self.store.update_device(
                    device_id,
                    {"desired_state": "disconnected", "observed_state": "disconnected"},
                )
            else:
                if action == "reconnect":
                    await self._stop_polling(device_id)
                    await self.adapter.disconnect()
                candidate = self._candidates.get(str(row["discovery_id"]))
                if candidate is None:
                    raise StateConflictError("a fresh scan is required before connecting")
                machine = ConnectionStateMachine()
                machine.discovered()
                machine.request_connect(force=action == "reconnect")
                machine.transition(ConnectionState.INITIALISING)
                await self.adapter.connect(candidate)
                machine.transition(ConnectionState.CONNECTED)
                machine.transition(ConnectionState.POLLING)
                await self.telemetry.record(device_id, await self.adapter.read_snapshot())
                self._connected_device = device_id
                self._start_polling(device_id)
                self.store.update_device(
                    device_id,
                    {"desired_state": "connected", "observed_state": machine.observed.value},
                )
        except Exception as exc:
            observed = "disconnected" if action == "disconnect" else "backoff"
            self.store.update_device(device_id, {"observed_state": observed})
            self._finish(operation, exc)
            return
        self._finish(operation)

    async def close(self) -> None:
        polling = tuple(self._polling_tasks.values())
        self._polling_tasks.clear()
        for task in polling:
            task.cancel()
        if polling:
            await asyncio.gather(*polling, return_exceptions=True)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.adapter.disconnect()
        await self.telemetry.close()

    def _start_polling(self, device_id: str) -> None:
        previous = self._polling_tasks.pop(device_id, None)
        if previous is not None:
            previous.cancel()
        task = asyncio.create_task(self._poll(device_id))
        self._polling_tasks[device_id] = task

        def discard(completed: asyncio.Task[None]) -> None:
            if self._polling_tasks.get(device_id) is completed:
                self._polling_tasks.pop(device_id, None)

        task.add_done_callback(discard)

    async def _stop_polling(self, device_id: str) -> None:
        task = self._polling_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _poll(self, device_id: str) -> None:
        while self._connected_device == device_id:
            await asyncio.sleep(self.poll_interval)
            if self._connected_device != device_id:
                return
            try:
                snapshot = await self.adapter.read_snapshot()
            except Exception:
                return
            await self.telemetry.record(device_id, snapshot)

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
