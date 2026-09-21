"""Current telemetry state, canonical events and stale-data transitions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from pitblu_core.events import EventBus, EventType, TelemetryEvent
from pitblu_core.models import DeviceSnapshot, TelemetrySource, utc_now


@dataclass(slots=True)
class _CurrentSnapshot:
    snapshot: DeviceSnapshot
    stale: bool = False


@dataclass(slots=True)
class _HeartbeatState:
    adapter_source: TelemetrySource
    status: str = "unknown"
    last_successful_communication_at: datetime | None = None
    successful_source: TelemetrySource | None = None
    sequence: int = 0


class TelemetryState:
    def __init__(
        self,
        events: EventBus,
        *,
        stale_after: float = 15,
        heartbeat_stale_after: float = 15,
    ) -> None:
        if min(stale_after, heartbeat_stale_after) <= 0:
            raise ValueError("stale thresholds must be positive")
        self.events = events
        self.stale_after = timedelta(seconds=stale_after)
        self.heartbeat_stale_after = timedelta(seconds=heartbeat_stale_after)
        self._current: dict[str, _CurrentSnapshot] = {}
        self._stale_tasks: dict[str, asyncio.Task[None]] = {}
        self._heartbeats: dict[str, _HeartbeatState] = {}
        self._heartbeat_stale_tasks: dict[str, asyncio.Task[None]] = {}
        self._event_sequences: dict[tuple[str, EventType, int | None], int] = {}

    def _sequence(
        self,
        device_id: str,
        event_type: EventType,
        probe: int | None,
        observed_sequence: int,
    ) -> int:
        key = (device_id, event_type, probe)
        sequence = max(observed_sequence, self._event_sequences.get(key, 0) + 1)
        self._event_sequences[key] = sequence
        return sequence

    async def record(self, device_id: str, snapshot: DeviceSnapshot) -> None:
        current = self._current.get(device_id)
        if current is not None and snapshot.observed_at <= current.snapshot.observed_at:
            await self.mark_stale()
            return
        if snapshot.successful_communication_at is not None:
            await self.communication_succeeded(
                device_id,
                snapshot.successful_communication_at,
                snapshot.source,
            )
        self._current[device_id] = _CurrentSnapshot(snapshot)
        previous = self._stale_tasks.pop(device_id, None)
        if previous is not None:
            previous.cancel()
        self._stale_tasks[device_id] = asyncio.create_task(
            self._mark_stale_after_deadline(device_id, snapshot)
        )
        common = {
            "source": snapshot.source,
            "device_id": device_id,
            "observed_at": snapshot.observed_at,
        }
        await self.events.publish(
            TelemetryEvent(
                type=EventType.DEVICE_AVAILABILITY,
                sequence=self._sequence(
                    device_id, EventType.DEVICE_AVAILABILITY, None, snapshot.sequence
                ),
                data={"available": any(probe.available for probe in snapshot.probes)},
                **common,
            )
        )
        await self.events.publish(
            TelemetryEvent(
                type=EventType.DEVICE_CONNECTION,
                sequence=self._sequence(
                    device_id, EventType.DEVICE_CONNECTION, None, snapshot.sequence
                ),
                data={"state": "polling"},
                **common,
            )
        )
        battery_time = snapshot.battery_observed_at or snapshot.observed_at
        previous_battery_time = (
            current.snapshot.battery_observed_at or current.snapshot.observed_at
            if current
            else None
        )
        if current is None or current.stale or battery_time != previous_battery_time:
            await self.events.publish(
                TelemetryEvent(
                    type=EventType.BATTERY,
                    sequence=self._sequence(device_id, EventType.BATTERY, None, snapshot.sequence),
                    data={
                        "available": snapshot.battery_available,
                        "percentage": snapshot.battery_percent,
                    },
                    **(common | {"observed_at": battery_time}),
                )
            )
        for probe in snapshot.probes:
            await self.events.publish(
                TelemetryEvent(
                    type=EventType.PROBE_AVAILABILITY,
                    sequence=self._sequence(
                        device_id, EventType.PROBE_AVAILABILITY, probe.number, probe.sequence
                    ),
                    probe=probe.number,
                    data={"available": probe.available, "present": probe.present},
                    **common,
                )
            )
            if probe.available and probe.present and probe.temperature_c is not None:
                await self.events.publish(
                    TelemetryEvent(
                        type=EventType.PROBE_TEMPERATURE,
                        sequence=self._sequence(
                            device_id, EventType.PROBE_TEMPERATURE, probe.number, probe.sequence
                        ),
                        probe=probe.number,
                        data={"temperatureC": probe.temperature_c},
                        **common,
                    )
                )

    async def mark_stale(
        self, now: datetime | None = None, *, force_device: str | None = None, reason: str = "stale"
    ) -> tuple[str, ...]:
        current_time = now or utc_now()
        changed: list[str] = []
        for device_id, current in self._current.items():
            snapshot = current.snapshot
            if current.stale or (
                device_id != force_device and current_time - snapshot.observed_at < self.stale_after
            ):
                continue
            current.stale = True
            changed.append(device_id)
            common = {
                "source": snapshot.source,
                "device_id": device_id,
                "observed_at": current_time,
            }
            await self.events.publish(
                TelemetryEvent(
                    type=EventType.DEVICE_AVAILABILITY,
                    sequence=self._sequence(
                        device_id, EventType.DEVICE_AVAILABILITY, None, snapshot.sequence
                    ),
                    data={"available": False, "reason": reason},
                    **common,
                )
            )
            await self.events.publish(
                TelemetryEvent(
                    type=EventType.BATTERY,
                    sequence=self._sequence(device_id, EventType.BATTERY, None, snapshot.sequence),
                    data={"available": False, "percentage": None, "reason": reason},
                    **common,
                )
            )
            for probe in snapshot.probes:
                await self.events.publish(
                    TelemetryEvent(
                        type=EventType.PROBE_AVAILABILITY,
                        sequence=self._sequence(
                            device_id,
                            EventType.PROBE_AVAILABILITY,
                            probe.number,
                            probe.sequence,
                        ),
                        probe=probe.number,
                        data={"available": False, "present": probe.present, "reason": reason},
                        **common,
                    )
                )
        return tuple(changed)

    async def _mark_stale_after_deadline(self, device_id: str, snapshot: DeviceSnapshot) -> None:
        delay = max(
            0.0,
            (snapshot.observed_at + self.stale_after - utc_now()).total_seconds(),
        )
        await asyncio.sleep(delay)
        current = self._current.get(device_id)
        if current is not None and current.snapshot is snapshot:
            await self.mark_stale()

    async def connection(self, device_id: str, state: str) -> None:
        current = self._current.get(device_id)
        if current is None:
            return
        snapshot = current.snapshot
        await self.events.publish(
            TelemetryEvent(
                type=EventType.DEVICE_CONNECTION,
                sequence=self._sequence(
                    device_id, EventType.DEVICE_CONNECTION, None, snapshot.sequence
                ),
                source=snapshot.source,
                device_id=device_id,
                data={"state": state},
            )
        )
        if state == "disconnected":
            await self.mark_stale(force_device=device_id, reason="disconnected")
            await self.events.publish(
                TelemetryEvent(
                    type=EventType.DEVICE_AVAILABILITY,
                    sequence=self._sequence(
                        device_id, EventType.DEVICE_AVAILABILITY, None, snapshot.sequence
                    ),
                    source=snapshot.source,
                    device_id=device_id,
                    data={"available": False, "reason": "disconnected"},
                )
            )

    def ensure_heartbeat(self, device_id: str, source: TelemetrySource) -> None:
        self._heartbeats.setdefault(device_id, _HeartbeatState(adapter_source=source))

    async def register_heartbeat(self, device_id: str, source: TelemetrySource) -> None:
        self.ensure_heartbeat(device_id, source)
        heartbeat = self._heartbeats[device_id]
        if heartbeat.sequence == 0:
            await self._publish_heartbeat(device_id, heartbeat, observed_at=utc_now())

    async def communication_succeeded(
        self,
        device_id: str,
        observed_at: datetime,
        source: TelemetrySource,
    ) -> None:
        if observed_at.tzinfo is None:
            raise ValueError("successful communication time must be timezone-aware")
        self.ensure_heartbeat(device_id, source)
        heartbeat = self._heartbeats[device_id]
        previous = heartbeat.last_successful_communication_at
        if previous is not None and observed_at <= previous:
            return
        heartbeat.status = "healthy"
        heartbeat.last_successful_communication_at = observed_at
        heartbeat.successful_source = source
        task = self._heartbeat_stale_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
        await self._publish_heartbeat(device_id, heartbeat, observed_at=observed_at)
        self._heartbeat_stale_tasks[device_id] = asyncio.create_task(
            self._mark_heartbeat_stale_after_deadline(device_id, observed_at)
        )

    async def heartbeat_disconnected(self, device_id: str) -> None:
        heartbeat = self._heartbeats.get(device_id)
        if heartbeat is None:
            return
        task = self._heartbeat_stale_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
        if heartbeat.status != "disconnected":
            heartbeat.status = "disconnected"
            await self._publish_heartbeat(device_id, heartbeat, observed_at=utc_now())

    async def heartbeat_expected(self, device_id: str) -> None:
        heartbeat = self._heartbeats.get(device_id)
        if heartbeat is None or heartbeat.status != "disconnected":
            return
        heartbeat.status = (
            "unknown" if heartbeat.last_successful_communication_at is None else "stale"
        )
        await self._publish_heartbeat(device_id, heartbeat, observed_at=utc_now())

    async def _mark_heartbeat_stale_after_deadline(
        self, device_id: str, successful_at: datetime
    ) -> None:
        delay = max(
            0.0,
            (successful_at + self.heartbeat_stale_after - utc_now()).total_seconds(),
        )
        await asyncio.sleep(delay)
        heartbeat = self._heartbeats.get(device_id)
        if (
            heartbeat is not None
            and heartbeat.status == "healthy"
            and heartbeat.last_successful_communication_at == successful_at
        ):
            heartbeat.status = "stale"
            await self._publish_heartbeat(device_id, heartbeat, observed_at=utc_now())

    async def _publish_heartbeat(
        self,
        device_id: str,
        heartbeat: _HeartbeatState,
        *,
        observed_at: datetime,
    ) -> None:
        heartbeat.sequence = self._sequence(
            device_id,
            EventType.THERMOMETER_HEARTBEAT,
            None,
            heartbeat.sequence + 1,
        )
        await self.events.publish(
            TelemetryEvent(
                type=EventType.THERMOMETER_HEARTBEAT,
                sequence=heartbeat.sequence,
                source=heartbeat.adapter_source,
                device_id=device_id,
                observed_at=observed_at,
                data=self._heartbeat_data(heartbeat),
            )
        )

    def _heartbeat_data(self, heartbeat: _HeartbeatState) -> dict[str, object]:
        return {
            "status": heartbeat.status,
            "lastSuccessfulCommunicationAt": (
                heartbeat.last_successful_communication_at.isoformat()
                if heartbeat.last_successful_communication_at is not None
                else None
            ),
            "fresh": heartbeat.status == "healthy",
            "staleAfterSeconds": self.heartbeat_stale_after.total_seconds(),
        }

    def heartbeat(self, device_id: str, *, desired_state: str) -> dict[str, object]:
        heartbeat = self._heartbeats.get(device_id)
        if heartbeat is None:
            raise KeyError(device_id)
        data = self._heartbeat_data(heartbeat)
        if desired_state == "disconnected":
            data["status"] = "disconnected"
            data["fresh"] = False
        elif heartbeat.status == "disconnected":
            data["status"] = (
                "unknown" if heartbeat.last_successful_communication_at is None else "stale"
            )
            data["fresh"] = False
        return data | {
            "sequence": max(1, heartbeat.sequence),
            "source": (
                heartbeat.successful_source.value
                if heartbeat.successful_source is not None
                else None
            ),
            "sessionId": self.events.session_id,
        }

    async def remove(self, device_id: str) -> None:
        await self.connection(device_id, "disconnected")
        await self.heartbeat_disconnected(device_id)
        task = self._stale_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
        heartbeat_task = self._heartbeat_stale_tasks.pop(device_id, None)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
        self._current.pop(device_id, None)
        self._heartbeats.pop(device_id, None)
        self.events.forget_device(device_id)
        self._event_sequences = {
            key: value for key, value in self._event_sequences.items() if key[0] != device_id
        }

    async def close(self) -> None:
        tasks = (*self._stale_tasks.values(), *self._heartbeat_stale_tasks.values())
        self._stale_tasks.clear()
        self._heartbeat_stale_tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def probes(self, device_id: str) -> list[dict[str, object]]:
        current = self._current.get(device_id)
        if current is None:
            return []
        return [
            {
                "probe": probe.number,
                "available": probe.available and not current.stale,
                "present": probe.present,
                "fresh": not current.stale,
                "temperatureC": None if current.stale else probe.temperature_c,
                "observedAt": probe.observed_at.isoformat(),
                "sequence": probe.sequence,
                "source": probe.source.value,
                "errorCode": "stale" if current.stale else probe.error_code,
            }
            for probe in current.snapshot.probes
        ]

    def observed_at(self, device_id: str) -> datetime | None:
        current = self._current.get(device_id)
        return current.snapshot.observed_at if current else None

    def battery(self, device_id: str) -> dict[str, object] | None:
        current = self._current.get(device_id)
        if current is None:
            return None
        snapshot = current.snapshot
        return {
            "available": snapshot.battery_available and not current.stale,
            "fresh": not current.stale,
            "percentage": None if current.stale else snapshot.battery_percent,
            "observedAt": (snapshot.battery_observed_at or snapshot.observed_at).isoformat(),
            "sequence": snapshot.sequence,
            "source": snapshot.source.value,
        }
