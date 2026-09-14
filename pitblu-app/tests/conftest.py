import pytest
from fastapi.testclient import TestClient

from pitblu_app.api import create_app
from pitblu_app.auth import AccessControl
from pitblu_app.store import Store


@pytest.fixture
def client():
    store = Store(":memory:")
    with TestClient(create_app(store=store, access=AccessControl.disabled())) as test_client:
        yield test_client
    store.close()


def create_active_cook(client, name="Saturday Brisket"):
    cook = client.post("/api/v1/cooks", json={"name": name}).json()
    assert client.post(f"/api/v1/cooks/{cook['id']}/start").status_code == 200
    return cook
