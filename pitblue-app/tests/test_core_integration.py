import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from pitblue_app.api import create_app
from pitblue_app.auth import AccessControl
from pitblue_app.store import Store


class ReconciledGateway:
    async def reconcile(self) -> list[dict[str, Any]]:
        return [
            {
                "deviceId": "device-a",
                "probes": [
                    {
                        "probe": 1,
                        "available": True,
                        "fresh": True,
                        "temperatureC": 68,
                        "observedAt": "2026-09-12T10:00:00+00:00",
                    }
                ],
            },
            {
                "deviceId": "device-b",
                "probes": [
                    {
                        "probe": 1,
                        "available": True,
                        "fresh": True,
                        "temperatureC": 126,
                        "observedAt": "2026-09-12T10:00:00+00:00",
                    }
                ],
            },
        ]

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        await asyncio.Event().wait()
        if False:  # pragma: no cover - makes this an async generator
            yield {}


class RecoveringGateway:
    def __init__(self) -> None:
        self.reconciliations = 0
        self.started_at = datetime.now(UTC)

    async def reconcile(self) -> list[dict[str, Any]]:
        self.reconciliations += 1
        return [
            {
                "deviceId": "device-a",
                "probes": [
                    {
                        "probe": 1,
                        "available": True,
                        "fresh": True,
                        "temperatureC": 68 if self.reconciliations == 1 else 72,
                        "observedAt": (
                            self.started_at + timedelta(seconds=self.reconciliations)
                        ).isoformat(),
                    }
                ],
            }
        ]

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self.reconciliations == 1:
            raise RuntimeError("simulated disconnect")
        await asyncio.Event().wait()
        if False:  # pragma: no cover - makes this an async generator
            yield {}


def prepared_store() -> Store:
    store = Store(":memory:")
    with store.transaction() as database:
        database.execute(
            "INSERT INTO cooks(id,name,state,created_at,started_at) VALUES(?,?,?,?,?)",
            (
                "cook",
                "Saturday",
                "active",
                "2026-09-12T09:00:00+00:00",
                "2026-09-12T09:00:00+00:00",
            ),
        )
        for measurement_id, label in (("food", "Brisket"), ("pit", "WSM")):
            database.execute(
                "INSERT INTO measurements(id,cook_id,label,kind,approaching_margin_c,range_persistence_seconds) VALUES(?,?,?,?,3,120)",
                (measurement_id, "cook", label, "food" if measurement_id == "food" else "cooker"),
            )
        database.execute(
            "INSERT INTO assignments VALUES(?,?,?,?,?,?,NULL)",
            ("one", "cook", "food", "device-a", 1, "2026-09-12T09:00:00+00:00"),
        )
        database.execute(
            "INSERT INTO assignments VALUES(?,?,?,?,?,?,NULL)",
            ("two", "cook", "pit", "device-b", 1, "2026-09-12T09:00:00+00:00"),
        )
    return store


def test_startup_reconciliation_keeps_same_channel_on_two_devices_distinct():
    store = prepared_store()
    with TestClient(
        create_app(store=store, core=ReconciledGateway(), access=AccessControl.disabled())
    ) as client:
        deadline = time.monotonic() + 1
        temperatures: dict[str, float | None] = {}
        while time.monotonic() < deadline:
            cook = client.get("/api/v1/cooks/cook").json()
            temperatures = {
                item["id"]: item["currentTemperatureC"] for item in cook["measurements"]
            }
            if temperatures == {"food": 68, "pit": 126}:
                break
            time.sleep(0.01)
        assert temperatures == {"food": 68, "pit": 126}
        readings = client.get("/api/v1/cooks/cook/telemetry").json()
        assert {(row["coreDeviceId"], row["probeChannel"]) for row in readings} == {
            ("device-a", 1),
            ("device-b", 1),
        }
    store.close()


def test_core_disconnect_records_a_gap_then_reconciles_after_reconnect():
    store = prepared_store()
    gateway = RecoveringGateway()
    with TestClient(
        create_app(
            store=store,
            core=gateway,
            access=AccessControl.disabled(),
            core_retry_seconds=0.01,
        )
    ) as client:
        deadline = time.monotonic() + 1
        readings: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            readings = client.get("/api/v1/cooks/cook/telemetry").json()
            if readings and gateway.reconciliations >= 2 and readings[-1]["temperatureC"] == 72:
                break
            time.sleep(0.01)

        assert gateway.reconciliations >= 2
        assert any(reading["available"] is False for reading in readings)
        assert readings[-1]["temperatureC"] == 72
        assert readings[-1]["available"] is True
    store.close()
