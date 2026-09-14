import asyncio
from datetime import UTC, datetime, timedelta

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


def test_event_retry_is_safe(client):
    cook = create_active_cook(client)
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
