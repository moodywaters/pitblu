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
