from pathlib import Path

import pytest

from pitboss_admin.storage import AdministrativeStore, VersionConflictError


def test_config_replacement_is_transactional_and_versioned() -> None:
    store = AdministrativeStore()
    assert store.config_state() == (1, {})
    assert store.replace_config({"server.port": "8081"}, 1) == 2
    assert store.config_state() == (2, {"server.port": "8081"})
    with pytest.raises(VersionConflictError) as error:
        store.replace_config({}, 1)
    assert error.value.current_version == 2
    assert store.config_state() == (2, {"server.port": "8081"})
    store.close()


def test_secret_values_are_internal_and_status_is_safe() -> None:
    store = AdministrativeStore()
    assert store.secret_status("mqtt.password") == (False, None)
    store.put_secret("mqtt.password", "not-returned-by-the-api", "now")
    assert store.secret_status("mqtt.password") == (True, "now")
    assert store.get_secret("mqtt.password") == "not-returned-by-the-api"
    assert store.delete_secret("mqtt.password")
    assert not store.delete_secret("mqtt.password")
    store.close()


def test_devices_and_operations_persist_without_telemetry(tmp_path: Path) -> None:
    path = tmp_path / "administrative.sqlite3"
    store = AdministrativeStore(path)
    device = {
        "device_id": "igrill-test",
        "discovery_id": "opaque",
        "name": "iGrill test",
        "friendly_name": None,
        "model": "igrill-v202",
        "auto_reconnect": True,
        "desired_state": "connected",
        "observed_state": "disconnected",
        "created_at": "2026-09-04T00:00:00+00:00",
    }
    store.save_device(device)
    operation = {
        "operation_id": "operation-test",
        "kind": "connect",
        "device_id": "igrill-test",
        "status": "succeeded",
        "created_at": "2026-09-04T00:00:00+00:00",
        "updated_at": "2026-09-04T00:00:01+00:00",
        "error_code": None,
    }
    store.save_operation(operation)
    store.close()

    reopened = AdministrativeStore(path)
    saved_device = reopened.device("igrill-test")
    saved_operation = reopened.operation("operation-test")
    assert saved_device is not None and saved_device["desired_state"] == "connected"
    assert saved_operation is not None and saved_operation["status"] == "succeeded"
    assert reopened.operations()[0]["operation_id"] == "operation-test"
    assert reopened.update_device("igrill-test", {"friendly_name": "Patio"})
    saved_device = reopened.device("igrill-test")
    assert saved_device is not None and saved_device["friendly_name"] == "Patio"
    assert reopened.delete_device("igrill-test")
    reopened.close()
