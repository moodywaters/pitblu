from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pitboss_admin.adapters.simulated import SimulatedIGrillAdapter
from pitboss_admin.api import create_app
from pitboss_admin.configuration import ConfigurationManager
from pitboss_admin.storage import AdministrativeStore


def client(*, authentication: bool = False) -> tuple[TestClient, AdministrativeStore]:
    store = AdministrativeStore()
    environment = {"PITBOSS_AUTH__MODE": "token"} if authentication else {}
    config = ConfigurationManager(store, environ=environment)
    app = create_app(adapter=SimulatedIGrillAdapter(4), store=store, configuration=config)
    return TestClient(app), store


def completed_operation(api: TestClient, operation_id: str) -> dict[str, Any]:
    for _ in range(50):
        operation = cast("dict[str, Any]", api.get(f"/api/v1/operations/{operation_id}").json())
        if operation["status"] in {"succeeded", "failed"}:
            return operation
    raise AssertionError("operation did not complete")


def test_device_and_operation_contract() -> None:
    api, store = client()
    with api:
        assert api.get("/health").json() == {"status": "ok"}
        assert api.get("/ready").status_code == 200
        assert api.get("/api/v1/bluetooth").json()["source"] == "simulated"

        scan = api.post("/api/v1/scans", json={}).json()
        assert scan["status"] in {"queued", "running", "succeeded"}
        assert completed_operation(api, scan["operationId"])["status"] == "succeeded"
        scan_result = api.get(f"/api/v1/scans/{scan['operationId']}").json()
        discovered = scan_result["devices"][0]
        assert "address" not in str(discovered).lower()

        created = api.post(
            "/api/v1/devices",
            json={"discoveryId": discovered["discoveryId"], "connect": True},
        )
        assert created.status_code == 201
        device_id = created.json()["device"]["deviceId"]
        connection = created.json()["operation"]
        assert completed_operation(api, connection["operationId"])["status"] == "succeeded"
        assert len(api.get(f"/api/v1/devices/{device_id}/probes").json()) == 4
        assert api.get(f"/api/v1/devices/{device_id}/battery").json()["percentage"] == 100

        patched = api.patch(
            f"/api/v1/devices/{device_id}",
            json={"friendlyName": "Patio thermometer", "automaticReconnection": False},
        ).json()
        assert patched["friendlyName"] == "Patio thermometer"
        assert not patched["automaticReconnection"]

        first = api.post(f"/api/v1/devices/{device_id}/disconnect")
        second = api.post(f"/api/v1/devices/{device_id}/disconnect")
        assert first.status_code == second.status_code == 202
        assert api.get("/api/v1/operations").json()
        assert api.get(f"/api/v1/operations/{first.json()['operationId']}").status_code == 200
        assert api.get("/api/v1/events").json() == []
        assert api.delete(f"/api/v1/devices/{device_id}").status_code == 204
    store.close()


def test_authentication_rotation_and_safe_errors() -> None:
    api, store = client(authentication=True)
    token: str = cast(FastAPI, api.app).state.bootstrap_token
    headers = {"Authorization": f"Bearer {token}"}
    with api:
        assert api.get("/health").status_code == 200
        unauthorised = api.get("/ready")
        assert unauthorised.status_code == 401
        assert unauthorised.json()["error"]["code"] == "authentication_required"
        assert "x-correlation-id" in unauthorised.headers
        assert api.get("/ready", headers=headers).status_code == 200

        rotation = api.post("/api/v1/auth/token/rotate", headers=headers)
        replacement = rotation.json()["token"]
        assert token not in str(store.auth_record())
        assert api.get("/ready", headers=headers).status_code == 401
        headers = {"Authorization": f"Bearer {replacement}"}
        assert api.get("/ready", headers=headers).status_code == 200

        missing = api.get("/api/v1/devices/not-found", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["correlationId"]
    store.close()


def test_configuration_concurrency_validation_and_secret_redaction() -> None:
    api, store = client()
    with api:
        response = api.get("/api/v1/config")
        assert response.headers["etag"] == '"1"'
        assert response.json()["settings"]["server.port"]["value"] == 8080
        assert response.json()["secrets"]["mqtt.password"]["configured"] is False
        assert api.post(
            "/api/v1/config/validate", json={"values": {"server.port": 8081}}
        ).json() == {"valid": True}

        missing_precondition = api.patch("/api/v1/config", json={"values": {"server.port": 8081}})
        assert missing_precondition.status_code == 409
        updated = api.patch(
            "/api/v1/config",
            headers={"If-Match": '"1"'},
            json={"values": {"server.port": 8081}},
        )
        assert updated.status_code == 200
        assert updated.headers["etag"] == '"2"'
        assert (
            api.patch(
                "/api/v1/config",
                headers={"If-Match": '"1"'},
                json={"values": {"server.port": 8082}},
            ).status_code
            == 409
        )

        secret_value = "must-never-be-returned"
        secret = api.put("/api/v1/config/secrets/mqtt.password", json={"value": secret_value})
        assert secret.status_code == 200
        assert secret_value not in secret.text
        assert api.get("/api/v1/config").json()["secrets"]["mqtt.password"]["configured"]
        assert api.delete("/api/v1/config/secrets/mqtt.password").json()["configured"] is False

        invalid: dict[str, Any] = {"values": {"server.port": 70000}}
        assert api.post("/api/v1/config/validate", json=invalid).status_code == 422

        echoed_secret = "x" * 4097
        rejected = api.put("/api/v1/config/secrets/mqtt.password", json={"value": echoed_secret})
        assert rejected.status_code == 422
        assert echoed_secret not in rejected.text
    store.close()
