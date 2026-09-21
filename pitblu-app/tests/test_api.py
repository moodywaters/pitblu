from conftest import create_active_cook


def test_health_openapi_and_system(client):
    health = client.get("/health", headers={"X-Correlation-ID": "test-request"})
    assert health.json() == {"status": "ok"}
    assert health.headers["X-Correlation-ID"] == "test-request"
    assert health.headers["Cache-Control"] == "no-store"
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    assert health.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in health.headers["Content-Security-Policy"]
    assert client.get("/openapi.json").status_code == 200
    system = client.get("/api/v1/system").json()
    assert system["product"] == "Pitblu"
    assert system["version"] == "0.5.0"


def test_system_exposes_latest_cook_for_completed_display_state(client):
    cook = create_active_cook(client)
    client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking")
    client.post(f"/api/v1/cooks/{cook['id']}/close")
    system = client.get("/api/v1/system").json()
    assert system["activeCook"] is None
    assert system["latestCook"] == {"id": cook["id"], "name": cook["name"], "state": "closed"}


def test_one_active_cook_and_full_lifecycle(client):
    cook = create_active_cook(client)
    other = client.post("/api/v1/cooks", json={"name": "Other"}).json()
    assert client.post(f"/api/v1/cooks/{other['id']}/start").status_code == 409
    assert (
        client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking").json()["state"]
        == "cooking_finished"
    )
    assert client.post(f"/api/v1/cooks/{cook['id']}/start-rest").json()["state"] == "resting"
    assert client.post(f"/api/v1/cooks/{cook['id']}/serve").json()["state"] == "served"
    assert client.post(f"/api/v1/cooks/{cook['id']}/close").json()["state"] == "closed"
    assert client.post(f"/api/v1/cooks/{cook['id']}/close").json()["state"] == "closed"


def test_cook_name_defaults_to_current_date(client):
    response = client.post("/api/v1/cooks", json={})
    assert response.status_code == 201
    assert response.json()["name"].startswith("Cook ")


def test_cook_can_snapshot_multiple_reusable_cookers(client):
    first = client.post("/api/v1/cooker-profiles", json={"name": "Kettle"}).json()
    second = client.post("/api/v1/cooker-profiles", json={"name": "WSM"}).json()
    response = client.post("/api/v1/cooks", json={"cookerProfileIds": [first["id"], second["id"]]})
    assert response.status_code == 201
    assert [item["name"] for item in response.json()["cookers"]] == ["Kettle", "WSM"]


def test_closed_cook_is_read_only(client):
    cook = create_active_cook(client)
    food = client.post(f"/api/v1/cooks/{cook['id']}/food-items", json={"name": "Brisket"}).json()
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Flat", "kind": "food", "foodItemId": food["id"]},
    ).json()
    client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking")
    client.post(f"/api/v1/cooks/{cook['id']}/close")
    assert client.patch(f"/api/v1/cooks/{cook['id']}", json={"name": "Changed"}).status_code == 409
    assert (
        client.patch(f"/api/v1/food-items/{food['id']}", json={"name": "Changed"}).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/v1/measurements/{measurement['id']}",
            json={"targetTemperatureC": 95},
        ).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/cooks/{cook['id']}/events", json={"type": "wrapped"}).status_code
        == 409
    )


def test_variable_domain_collections(client):
    cook = client.post("/api/v1/cooks", json={"name": "Big Cook"}).json()
    cooker_ids = [
        client.post(f"/api/v1/cooks/{cook['id']}/cookers", json={"name": n}).json()["id"]
        for n in ("WSM", "Kettle")
    ]
    foods = [
        client.post(f"/api/v1/cooks/{cook['id']}/food-items", json={"name": f"Food {n}"}).json()
        for n in range(6)
    ]
    for n, food in enumerate(foods):
        response = client.post(
            f"/api/v1/cooks/{cook['id']}/measurements",
            json={
                "label": f"Point {n}",
                "kind": "food",
                "cookerId": cooker_ids[n % 2],
                "foodItemId": food["id"],
                "targetTemperatureC": 93,
            },
        )
        assert response.status_code == 201
    assert len(client.get(f"/api/v1/cooks/{cook['id']}").json()["measurements"]) == 6
    assert (
        client.patch(f"/api/v1/cookers/{cooker_ids[0]}", json={"name": "WSM 57"}).json()["name"]
        == "WSM 57"
    )
    assert (
        client.patch(f"/api/v1/food-items/{foods[0]['id']}", json={"name": "Brisket"}).json()[
            "name"
        ]
        == "Brisket"
    )


def test_reusable_cooker_profile_is_snapshotted_into_each_cook(client):
    profile = client.post(
        "/api/v1/cooker-profiles",
        json={"name": "WSM 57", "description": "Charcoal smoker"},
    ).json()
    first = client.post(
        "/api/v1/cooks", json={"name": "Brisket", "cookerProfileId": profile["id"]}
    ).json()
    second = client.post(
        "/api/v1/cooks", json={"name": "Ribs", "cookerProfileId": profile["id"]}
    ).json()

    assert first["cookers"][0]["name"] == "WSM 57"
    assert second["cookers"][0]["profileId"] == profile["id"]
    updated = client.patch(
        f"/api/v1/cooker-profiles/{profile['id']}", json={"name": "WSM 57 Classic"}
    ).json()
    assert updated["name"] == "WSM 57 Classic"
    assert client.get(f"/api/v1/cooks/{first['id']}").json()["cookers"][0]["name"] == "WSM 57"


def test_invalid_range_is_rejected(client):
    cook = client.post("/api/v1/cooks", json={"name": "Cook"}).json()
    response = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Pit", "kind": "cooker", "rangeMinC": 140, "rangeMaxC": 120},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["correlationId"]


def test_invalid_range_patch_is_rejected(client):
    cook = client.post("/api/v1/cooks", json={"name": "Cook"}).json()
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Pit", "kind": "cooker", "rangeMinC": 120, "rangeMaxC": 135},
    ).json()
    response = client.patch(f"/api/v1/measurements/{measurement['id']}", json={"rangeMinC": 140})
    assert response.status_code == 422


def test_measurement_cooker_context_can_change_without_reassigning_probe(client):
    cook = client.post("/api/v1/cooks", json={"name": "Brisket"}).json()
    first = client.post(f"/api/v1/cooks/{cook['id']}/cookers", json={"name": "WSM"}).json()
    second = client.post(f"/api/v1/cooks/{cook['id']}/cookers", json={"name": "Oven"}).json()
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Brisket", "kind": "food", "cookerId": first["id"]},
    ).json()
    assignment = client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "igrill", "probeChannel": 6},
    ).json()

    changed = client.patch(
        f"/api/v1/measurements/{measurement['id']}", json={"cookerId": second["id"]}
    ).json()

    assert changed["cookerId"] == second["id"]
    assert client.get(f"/api/v1/cooks/{cook['id']}/assignments").json() == [assignment]
    other_cook = client.post("/api/v1/cooks", json={"name": "Other"}).json()
    foreign = client.post(
        f"/api/v1/cooks/{other_cook['id']}/cookers", json={"name": "Foreign cooker"}
    ).json()
    rejected = client.patch(
        f"/api/v1/measurements/{measurement['id']}", json={"cookerId": foreign["id"]}
    )
    assert rejected.status_code == 422


def test_close_ends_active_assignments_at_the_close_timestamp(client):
    cook = create_active_cook(client)
    measurement = client.post(
        f"/api/v1/cooks/{cook['id']}/measurements",
        json={"label": "Brisket", "kind": "food"},
    ).json()
    client.post(
        f"/api/v1/cooks/{cook['id']}/assignments",
        json={"measurementId": measurement["id"], "coreDeviceId": "igrill", "probeChannel": 12},
    )
    client.post(f"/api/v1/cooks/{cook['id']}/finish-cooking")

    closed = client.post(f"/api/v1/cooks/{cook['id']}/close").json()
    assignments = client.get(f"/api/v1/cooks/{cook['id']}/assignments").json()

    assert assignments[0]["endedAt"] == closed["closedAt"]


def test_draft_cook_cannot_steal_source_from_active_cook(client):
    active = create_active_cook(client)
    first = client.post(
        f"/api/v1/cooks/{active['id']}/measurements",
        json={"label": "Brisket", "kind": "food"},
    ).json()
    client.post(
        f"/api/v1/cooks/{active['id']}/assignments",
        json={
            "measurementId": first["id"],
            "coreDeviceId": "device-a",
            "probeChannel": 1,
        },
    )
    draft = client.post("/api/v1/cooks", json={"name": "Tomorrow"}).json()
    second = client.post(
        f"/api/v1/cooks/{draft['id']}/measurements",
        json={"label": "Chicken", "kind": "food"},
    ).json()
    response = client.post(
        f"/api/v1/cooks/{draft['id']}/assignments",
        json={
            "measurementId": second["id"],
            "coreDeviceId": "device-a",
            "probeChannel": 1,
        },
    )
    assert response.status_code == 409
    active_assignments = client.get(f"/api/v1/cooks/{active['id']}/assignments").json()
    assert active_assignments[0]["endedAt"] is None
