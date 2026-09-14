from pathlib import Path

from fastapi.testclient import TestClient

from pitblu_app.api import create_app
from pitblu_app.auth import AccessControl, Scope
from pitblu_app.store import Store

OPERATOR = "operator-token-that-is-at-least-32-characters"
DISPLAY = "display-token-that-is-at-least-32-characters"
INTEGRATION = "integration-token-that-is-at-least-32-characters"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def secured_client(tmp_path):
    store = Store(tmp_path / "auth.sqlite3")
    access = AccessControl(
        {
            Scope.OPERATOR: OPERATOR,
            Scope.DISPLAY: DISPLAY,
            Scope.INTEGRATION: INTEGRATION,
        }
    )
    return TestClient(create_app(store=store, access=access)), store


def test_public_surfaces_do_not_issue_credentials(tmp_path):
    client, store = secured_client(tmp_path)
    with client:
        assert client.get("/health").status_code == 200
        display = client.get("/display")
        assert display.status_code == 200
        assert "set-cookie" not in display.headers
        assert client.get("/manifest.webmanifest").status_code == 200
        assert client.get("/pitblu-logo.png").status_code == 200
        assert client.get("/sw.js").status_code == 200
        assert client.get("/index.html").status_code == 200
        asset_name = next(
            path.name
            for path in (
                Path(__file__).parents[1] / "src" / "pitblu_app" / "static" / "assets"
            ).glob("index-*.js")
        )
        assert client.get(f"/assets/{asset_name}").headers["cache-control"].endswith("immutable")
        denied = client.get("/api/v1/system")
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"] == "Bearer"
        assert denied.json()["error"]["code"] == "authentication_required"
    store.close()


def test_operator_has_full_api_access(tmp_path):
    client, store = secured_client(tmp_path)
    with client:
        created = client.post(
            "/api/v1/cooks", json={"name": "Authenticated cook"}, headers=bearer(OPERATOR)
        )
        assert created.status_code == 201
        assert client.get("/api/v1/system", headers=bearer(OPERATOR)).status_code == 200
    store.close()


def test_openapi_documents_bearer_and_public_follower_scope(tmp_path):
    client, store = secured_client(tmp_path)
    with client:
        schema = client.get("/openapi.json", headers=bearer(OPERATOR)).json()
        scheme = schema["components"]["securitySchemes"]["PitbluBearer"]
        assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
        assert schema["paths"]["/api/v1/cooks"]["post"]["security"] == [{"PitbluBearer": []}]
        assert schema["paths"]["/api/v1/follow/{token}"]["get"]["security"] == []
    store.close()


def test_display_token_is_read_only(tmp_path):
    client, store = secured_client(tmp_path)
    with client:
        assert client.get("/api/v1/system", headers=bearer(DISPLAY)).status_code == 200
        denied = client.post("/api/v1/cooks", json={"name": "Not allowed"}, headers=bearer(DISPLAY))
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "insufficient_scope"

        cook = client.post(
            "/api/v1/cooks", json={"name": "Display cook"}, headers=bearer(OPERATOR)
        ).json()
        client.post(f"/api/v1/cooks/{cook['id']}/start", headers=bearer(OPERATOR))
        default = client.get(f"/api/v1/cooks/{cook['id']}/default-share", headers=bearer(DISPLAY))
        assert default.status_code == 200 and default.json()["isDefault"] is True
        assert (
            client.post(
                f"/api/v1/cooks/{cook['id']}/shares", json={}, headers=bearer(DISPLAY)
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/cooks/{cook['id']}/default-share/regenerate", headers=bearer(DISPLAY)
            ).status_code
            == 403
        )
        assert (
            client.delete(
                f"/api/v1/shares/{default.json()['id']}", headers=bearer(DISPLAY)
            ).status_code
            == 403
        )
    store.close()


def test_integration_token_is_limited_to_events_and_lifecycle(tmp_path):
    client, store = secured_client(tmp_path)
    with client:
        cook = client.post(
            "/api/v1/cooks", json={"name": "Integration cook"}, headers=bearer(OPERATOR)
        ).json()
        denied = client.post(
            f"/api/v1/cooks/{cook['id']}/measurements",
            json={"label": "Food", "kind": "food"},
            headers=bearer(INTEGRATION),
        )
        assert denied.status_code == 403
        started = client.post(f"/api/v1/cooks/{cook['id']}/start", headers=bearer(INTEGRATION))
        assert started.status_code == 200
        event = client.post(
            f"/api/v1/cooks/{cook['id']}/events",
            json={"type": "wrapped"},
            headers=bearer(INTEGRATION),
        )
        assert event.status_code == 201
    store.close()


def test_environment_tokens_are_required_distinct_and_long(monkeypatch):
    monkeypatch.delenv("PITBLU_APP_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("PITBLU_APP_DISPLAY_TOKEN", raising=False)
    try:
        AccessControl.from_environment()
    except RuntimeError as exc:
        assert "at least 32 characters" in str(exc)
    else:
        raise AssertionError("missing tokens must prevent startup")

    monkeypatch.setenv("PITBLU_APP_OPERATOR_TOKEN", OPERATOR)
    monkeypatch.setenv("PITBLU_APP_DISPLAY_TOKEN", OPERATOR)
    try:
        AccessControl.from_environment()
    except RuntimeError as exc:
        assert "distinct" in str(exc)
    else:
        raise AssertionError("duplicate tokens must prevent startup")
