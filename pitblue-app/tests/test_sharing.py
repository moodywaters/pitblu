import asyncio
from datetime import UTC, datetime

from conftest import create_active_cook
from fastapi.testclient import TestClient

from pitblue_app.api import create_app
from pitblue_app.auth import AccessControl
from pitblue_app.models import TelemetryIn
from pitblue_app.store import Store


def test_follower_is_random_read_only_revocable_and_expires(client):
    cook = create_active_cook(client)
    one = client.post(f"/api/v1/cooks/{cook['id']}/shares", json={}).json()
    two = client.post(f"/api/v1/cooks/{cook['id']}/shares", json={}).json()
    assert one["token"] != two["token"] and len(one["token"]) >= 40
    shares = client.get(f"/api/v1/cooks/{cook['id']}/shares").json()
    assert len(shares) == 3
    assert len([share for share in shares if share["isDefault"]]) == 1
    follower_api = f"/api/v1/follow/{one['token']}"
    follower = client.get(follower_api)
    assert follower.status_code == 200
    assert "assignments" not in follower.json()
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Brisket", "kind": "food", "targetTemperatureC": 93},
    ).json()
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={
            "measurementId": measurement["id"],
            "coreDeviceId": "private-device",
            "probeChannel": 2,
        },
    )
    asyncio.run(
        client.app.state.service.ingest(
            TelemetryIn(
                coreDeviceId="private-device",
                probeChannel=2,
                temperatureC=68,
                observedAt=datetime.now(UTC),
                eventId="follower-reading",
            )
        )
    )
    client.post(f"/api/v1/cooks/{cook['id']}/events", json={"type": "wrapped"})
    follower_readings = client.get(f"{follower_api}/telemetry").json()
    assert follower_readings[0]["measurementId"] == measurement["id"]
    assert "coreDeviceId" not in follower_readings[0]
    assert "probeChannel" not in follower_readings[0]
    assert "assignmentId" not in follower_readings[0]
    assert "receivedAt" not in follower_readings[0]
    follower_events = client.get(f"{follower_api}/events").json()
    assert follower_events[-1]["type"] == "wrapped"
    qr = client.get(f"/api/v1/shares/qr/{one['token']}")
    assert qr.status_code == 200
    assert qr.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in qr.content
    assert client.post(follower_api, json={}).status_code == 405
    assert client.delete(f"/api/v1/shares/{one['id']}").status_code == 204
    assert client.get(follower_api).status_code == 404
    assert client.get(f"{follower_api}/telemetry").status_code == 404
    client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking")
    client.post(f"/api/v1/cooks/{cook['id']}/close")
    assert client.get(f"/api/v1/follow/{two['token']}").status_code == 404


def test_draft_cook_cannot_be_shared(client):
    cook = client.post("/api/v1/cooks", json={"name": "Draft"}).json()
    response = client.post(f"/api/v1/cooks/{cook['id']}/shares", json={})
    assert response.status_code == 409


def test_default_share_is_lifecycle_managed_repairable_and_regenerable(client):
    cook = create_active_cook(client)
    default = client.get(f"/api/v1/cooks/{cook['id']}/default-share").json()
    assert default["isDefault"] is True
    assert len(default["token"].split(".")) == 2
    assert client.get(f"/api/v1/follow/{default['token']}").status_code == 200

    regenerated = client.post(f"/api/v1/cooks/{cook['id']}/default-share/regenerate").json()
    assert regenerated["token"] != default["token"]
    assert client.get(f"/api/v1/follow/{default['token']}").status_code == 404
    assert client.get(f"/api/v1/follow/{regenerated['token']}").status_code == 200

    with client.app.state.store.transaction() as database:
        database.execute(
            "UPDATE follower_shares SET revoked_at=? WHERE id=?",
            (datetime.now(UTC).isoformat(), regenerated["id"]),
        )
    repaired = client.get(f"/api/v1/cooks/{cook['id']}/default-share").json()
    assert repaired["token"] != regenerated["token"]

    client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking")
    client.post(f"/api/v1/cooks/{cook['id']}/close")
    assert client.get(f"/api/v1/follow/{repaired['token']}").status_code == 404


def test_default_share_is_reconstructed_during_startup_reconciliation(tmp_path):
    path = tmp_path / "restart.sqlite3"
    first_store = Store(path)
    with TestClient(create_app(store=first_store, access=AccessControl.disabled())) as first_client:
        cook = create_active_cook(first_client)
        original = first_client.get(f"/api/v1/cooks/{cook['id']}/default-share").json()
    first_store.close()

    second_store = Store(path)
    with TestClient(
        create_app(store=second_store, access=AccessControl.disabled())
    ) as second_client:
        restored = second_client.get(f"/api/v1/cooks/{cook['id']}/default-share").json()
        assert restored["id"] == original["id"]
        assert restored["token"] == original["token"]
    second_store.close()
