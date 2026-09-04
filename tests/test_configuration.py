import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pitboss_admin.configuration import ConfigurationManager
from pitboss_admin.storage import AdministrativeStore, VersionConflictError


def test_configuration_layers_and_metadata(tmp_path: Path) -> None:
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text("bluetooth:\n  scan_duration: 7\n", encoding="utf-8")
    store = AdministrativeStore()
    manager = ConfigurationManager(
        store, yaml_path=yaml_path, environ={"PITBOSS_MQTT__ENABLED": "true"}
    )
    description = manager.describe()
    assert description["settings"]["bluetooth.scan_duration"]["source"] == "yaml"
    assert description["settings"]["mqtt.enabled"]["value"] is True
    assert description["settings"]["server.port"]["default"] == 8080

    manager.update({"bluetooth.scan_duration": 8}, expected_version=1)
    assert manager.version == 2
    assert manager.describe()["settings"]["bluetooth.scan_duration"]["source"] == (
        "persisted_override"
    )
    with pytest.raises(VersionConflictError):
        manager.update({}, expected_version=1)
    store.close()


def test_configuration_validation_is_whole_and_secure() -> None:
    store = AdministrativeStore()
    manager = ConfigurationManager(store, environ={})
    with pytest.raises(ValidationError, match="token authentication"):
        manager.validate_patch({"server.bind": "0.0.0.0"})
    accepted = manager.validate_patch(
        {"server.bind": "0.0.0.0", "auth.mode": "token", "server.port": 8081}
    )
    assert accepted.server.port == 8081
    with pytest.raises(ValueError, match="unknown"):
        manager.validate_patch({"unknown": True})
    assert manager.version == 1
    store.close()


def test_persisted_overrides_survive_manager_recreation() -> None:
    store = AdministrativeStore()
    manager = ConfigurationManager(store, environ={})
    manager.update({"simulation.enabled": True}, 1)
    recreated = ConfigurationManager(store, environ={})
    assert recreated.config.simulation.enabled
    assert json.loads(store.config_state()[1]["simulation.enabled"]) is True
    store.close()
