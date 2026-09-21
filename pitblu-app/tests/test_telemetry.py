import asyncio
from datetime import UTC, datetime, timedelta, timezone

from conftest import create_active_cook

from pitblu_app.models import TelemetryIn


def setup_measurement(client):
    cook = create_active_cook(client)
    food = client.post(f"/api/v1/cooks/{cook['id']}/food-items", json={"name": "Brisket"}).json()
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={
            "label": "Brisket Flat",
            "kind": "food",
            "foodItemId": food["id"],
            "targetTemperatureC": 93,
        },
    ).json()
    return cook, measurement


def ingest(client, device, channel, temp, when, event):
    return asyncio.run(
        client.app.state.service.ingest(
            TelemetryIn(
                coreDeviceId=device,
                probeChannel=channel,
                temperatureC=temp,
                observedAt=when,
                available=temp is not None,
                eventId=event,
            )
        )
    )


def test_device_plus_channel_identity_and_reassignment_history(client):
    cook, first = setup_measurement(client)
    second = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Chicken", "kind": "food", "targetTemperatureC": 74},
    ).json()
    a1 = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": first["id"], "coreDeviceId": "abc", "probeChannel": 1},
    ).json()
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": second["id"], "coreDeviceId": "xyz", "probeChannel": 1},
    )
    now = datetime.now(UTC)
    ingest(client, "abc", 1, 68, now, "e1")
    ingest(client, "xyz", 1, 67, now, "e2")
    client.delete(f"/api/v1/assignments/{a1['id']}")
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": second["id"], "coreDeviceId": "abc", "probeChannel": 1},
    )
    ingest(client, "abc", 1, 69, now + timedelta(minutes=1), "e3")
    history = client.get(f"/api/v1/cooks/{cook['id']}/telemetry").json()
    assert [(x["coreDeviceId"], x["measurementId"]) for x in history] == [
        ("abc", first["id"]),
        ("xyz", second["id"]),
        ("abc", second["id"]),
    ]
    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert len(assignments) == 3


def test_assignment_history_uses_observation_time_and_preserves_unassigned_gaps(client):
    cook, brisket = setup_measurement(client)
    ambient = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "WSM Ambient", "kind": "cooker", "rangeMinC": 120, "rangeMaxC": 135},
    ).json()
    first = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": brisket["id"], "coreDeviceId": "igrill-a", "probeChannel": 17},
    ).json()
    base = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    store = client.app.state.store
    with store.transaction() as database:
        database.execute(
            "UPDATE assignments SET started_at=?,ended_at=? WHERE id=?",
            (base.isoformat(), (base + timedelta(minutes=10)).isoformat(), first["id"]),
        )
    second = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": ambient["id"], "coreDeviceId": "igrill-a", "probeChannel": 17},
    ).json()
    with store.transaction() as database:
        database.execute(
            "UPDATE assignments SET started_at=? WHERE id=?",
            ((base + timedelta(minutes=20)).isoformat(), second["id"]),
        )

    ingest(client, "igrill-a", 17, 68, base + timedelta(minutes=5), "brisket-live")
    ingest(client, "igrill-a", 17, 70, base + timedelta(minutes=9), "brisket-newest")
    ingest(client, "igrill-a", 17, 25, base + timedelta(minutes=15), "unassigned-gap")
    ingest(client, "igrill-a", 17, 122, base + timedelta(minutes=25), "ambient-live")
    # This older sample arrives after reassignment but still belongs to the first assignment.
    delayed = (base + timedelta(minutes=8)).astimezone(timezone(timedelta(hours=2)))
    ingest(client, "igrill-a", 17, 69, delayed, "brisket-delayed")

    readings = client.get(f"/api/v1/cooks/{cook['id']}/telemetry").json()
    assert [(row["measurementId"], row["assignmentId"]) for row in readings] == [
        (brisket["id"], first["id"]),
        (brisket["id"], first["id"]),
        (brisket["id"], first["id"]),
        (None, None),
        (ambient["id"], second["id"]),
    ]
    assert all(row["coreDeviceId"] == "igrill-a" for row in readings)
    assert all(row["probeChannel"] == 17 for row in readings)
    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert [item["id"] for item in assignments] == [first["id"], second["id"]]
    assert client.get(f"/api/v1/measurements/{brisket['id']}").json()["currentTemperatureC"] == 70


def test_explicit_replacement_ends_conflicting_assignment_at_new_start(client):
    cook, first_measurement = setup_measurement(client)
    second_measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "WSM Ambient", "kind": "cooker"},
    ).json()
    first = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": first_measurement["id"], "coreDeviceId": "igrill", "probeChannel": 11},
    ).json()
    second = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": second_measurement["id"], "coreDeviceId": "igrill", "probeChannel": 11},
    ).json()

    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert assignments[0]["id"] == first["id"]
    assert assignments[0]["endedAt"] == second["startedAt"]
    assert assignments[1]["id"] == second["id"]
    assert assignments[1]["endedAt"] is None


def test_one_measurement_can_be_fed_by_different_physical_probes(client):
    cook, measurement = setup_measurement(client)
    first = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "device-a", "probeChannel": 2},
    ).json()
    client.delete(f"/api/v1/assignments/{first['id']}")
    second = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "device-b", "probeChannel": 4},
    ).json()
    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert assignments[0]["endedAt"] is not None
    assert assignments[1]["endedAt"] is None
    assert {(item["coreDeviceId"], item["probeChannel"]) for item in assignments} == {
        ("device-a", 2),
        ("device-b", 4),
    }
    assert second["measurementId"] == measurement["id"]


def test_targets_alerts_stale_and_idempotence(client):
    cook, measurement = setup_measurement(client)
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "abc", "probeChannel": 2},
    )
    now = datetime.now(UTC)
    assert ingest(client, "abc", 2, 90, now, "approach") is not None
    active = client.get("/api/v1/alerts?active=true").json()
    assert active[0]["type"] == "temperature.approaching_target"
    assert (
        client.post(f"/api/v1/alerts/{active[0]['id']}/acknowledge").json()["status"]
        == "acknowledged"
    )
    ingest(client, "abc", 2, 93, now + timedelta(minutes=1), "target")
    types = {
        a["type"]: a["status"] for a in client.get(f"/api/v1/alerts?cookId={cook['id']}").json()
    }
    assert types["temperature.approaching_target"] == "resolved"
    assert types["temperature.target_reached"] == "active"
    count = len(client.get(f"/api/v1/cooks/{cook['id']}/telemetry").json())
    ingest(client, "abc", 2, 93, now + timedelta(minutes=1), "target")
    assert len(client.get(f"/api/v1/cooks/{cook['id']}/telemetry").json()) == count
    ingest(client, "abc", 2, None, now + timedelta(minutes=2), "missing")
    assert (
        client.get(f"/api/v1/measurements/{measurement['id']}").json()["interpretedState"]
        == "unavailable"
    )
    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert len(assignments) == 1
    assert assignments[0]["endedAt"] is None


def test_event_retry_is_safe(client):
    cook = create_active_cook(client)
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Brisket", "kind": "food"},
    ).json()
    assignment = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "abc", "probeChannel": 9},
    ).json()
    headers = {"Idempotency-Key": "button-press-1"}
    one = client.post(
        f"/api/v1/cooks/{cook['id']}/events", json={"type": "wrapped"}, headers=headers
    ).json()
    two = client.post(
        f"/api/v1/cooks/{cook['id']}/events", json={"type": "wrapped"}, headers=headers
    ).json()
    assert one["id"] == two["id"]
    events = client.get(f"/api/v1/cooks/{cook['id']}/events").json()
    assert len([event for event in events if event["type"] == "wrapped"]) == 1
    current = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()
    assert current == [assignment]


def test_repeated_alert_cycles_are_retained(client):
    cook, measurement = setup_measurement(client)
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={
            "measurementId": measurement["id"],
            "coreDeviceId": "abc",
            "probeChannel": 1,
        },
    )
    now = datetime.now(UTC)
    ingest(client, "abc", 1, 93, now, "cycle-1-high")
    ingest(client, "abc", 1, 80, now + timedelta(minutes=1), "cycle-1-low")
    ingest(client, "abc", 1, 94, now + timedelta(minutes=2), "cycle-2-high")
    alerts = client.get(f"/api/v1/alerts?cookId={cook['id']}").json()
    reached = [alert for alert in alerts if alert["type"] == "temperature.target_reached"]
    assert [alert["status"] for alert in reached] == ["active", "resolved"]


def test_cooker_range_waits_for_persistence(client):
    cook = create_active_cook(client)
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={
            "label": "WSM Ambient",
            "kind": "cooker",
            "rangeMinC": 120,
            "rangeMaxC": 135,
            "rangePersistenceSeconds": 120,
        },
    ).json()
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={
            "measurementId": measurement["id"],
            "coreDeviceId": "abc",
            "probeChannel": 1,
        },
    )
    now = datetime.now(UTC)
    ingest(client, "abc", 1, 110, now, "range-low-first")
    assert not any(
        alert["type"] == "temperature.below_range"
        for alert in client.get("/api/v1/alerts?active=true").json()
    )
    store = client.app.state.store
    with store.transaction() as database:
        database.execute(
            "UPDATE measurements SET out_of_range_since=? WHERE id=?",
            ((now - timedelta(minutes=3)).isoformat(), measurement["id"]),
        )
    ingest(client, "abc", 1, 109, now + timedelta(seconds=5), "range-low-persisted")
    assert any(
        alert["type"] == "temperature.below_range"
        for alert in client.get("/api/v1/alerts?active=true").json()
    )


def test_telemetry_downsampling_is_bounded(client):
    cook, measurement = setup_measurement(client)
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={
            "measurementId": measurement["id"],
            "coreDeviceId": "abc",
            "probeChannel": 1,
        },
    )
    now = datetime.now(UTC)
    for index in range(20):
        ingest(client, "abc", 1, 50 + index, now + timedelta(minutes=index), f"p-{index}")
    sampled = client.get(f"/api/v1/cooks/{cook['id']}/telemetry?maxPoints=5").json()
    assert len(sampled) <= 5
    assert sampled[0]["temperatureC"] == 50
    assert sampled[-1]["temperatureC"] == 69
