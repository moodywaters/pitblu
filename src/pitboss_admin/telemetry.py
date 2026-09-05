"""Current telemetry state, canonical events and stale-data transitions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from pitboss_admin.events import EventBus, EventType, TelemetryEvent
from pitboss_admin.models import DeviceSnapshot, utc_now


@dataclass(slots=True)
class _CurrentSnapshot:
    snapshot: DeviceSnapshot
    stale: bool = False


class TelemetryState:
    def __init__(self, events: EventBus, *, stale_after: float = 15) -> None:
        if stale_after <= 0:
            raise ValueError("stale threshold must be positive")
        self.events = events
        self.stale_after = timedelta(seconds=stale_after)
        self._current: dict[str, _CurrentSnapshot] = {}
        self._stale_tasks: dict[str, asyncio.Task[None]] = {}
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
        await self.events.publish(
            TelemetryEvent(
                type=EventType.BATTERY,
                sequence=self._sequence(device_id, EventType.BATTERY, None, snapshot.sequence),
                data={
                    "available": snapshot.battery_available,
                    "percentage": snapshot.battery_percent,
                },
                **common,
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

    async def remove(self, device_id: str) -> None:
        await self.connection(device_id, "disconnected")
        task = self._stale_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
        self._current.pop(device_id, None)
        self.events.forget_device(device_id)
        self._event_sequences = {
            key: value for key, value in self._event_sequences.items() if key[0] != device_id
        }

    async def close(self) -> None:
        tasks = tuple(self._stale_tasks.values())
        self._stale_tasks.clear()
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
            "observedAt": snapshot.observed_at.isoformat(),
            "sequence": snapshot.sequence,
            "source": snapshot.source.value,
        }
