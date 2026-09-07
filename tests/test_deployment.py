import io
import sqlite3
import sys
from pathlib import Path

import pytest

from pitboss_admin.auth import AdministratorTokens
from pitboss_admin.deployment import backup_database, bootstrap, main, startup_configuration
from pitboss_admin.storage import AdministrativeStore


def test_managed_startup_never_bootstraps_token(tmp_path: Path) -> None:
    store = AdministrativeStore()
    try:
        with pytest.raises(ValueError, match="bootstrap"):
            startup_configuration(store, {"PITBOSS_MANAGED": "true", "PITBOSS_AUTH__MODE": "token"})
        assert not AdministratorTokens(store).status().configured
        AdministratorTokens(store).bootstrap()
        yaml = tmp_path / "config.yaml"
        yaml.write_text("server:\n  bind: 127.0.0.1\n  port: 8091\n", encoding="utf-8")
        config = startup_configuration(
            store,
            {
                "PITBOSS_MANAGED": "true",
                "PITBOSS_CONFIG_FILE": str(yaml),
                "PITBOSS_AUTH__MODE": "token",
            },
        )
        assert config.config.server.port == 8091
        assert config.describe()["settings"]["server.port"]["source"] == "yaml"
        with pytest.raises(ValueError, match="requires token"):
            startup_configuration(
                store,
                {
                    "PITBOSS_MANAGED": "true",
                    "PITBOSS_AUTH__MODE": "disabled",
                    "PITBOSS_SERVER__BIND": "127.0.0.1",
                },
            )
        with pytest.raises(ValueError, match="missing"):
            startup_configuration(store, {"PITBOSS_CONFIG_FILE": str(tmp_path / "missing")})
    finally:
        store.close()


def test_bootstrap_refuses_redirected_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="terminal"):
        bootstrap(tmp_path / "state.sqlite3")
    assert not (tmp_path / "state.sqlite3").exists()


def test_backup_preserves_secrets_without_overwrite(tmp_path: Path) -> None:
    original = tmp_path / "state.sqlite3"
    saved = tmp_path / "backup.sqlite3"
    store = AdministrativeStore(original)
    try:
        store.put_secret("mqtt.password", "test-only-secret", "2026-09-07T00:00:00+00:00")
        backup_database(original, saved)
        restored = AdministrativeStore(saved)
        try:
            assert restored.get_secret("mqtt.password") == "test-only-secret"
        finally:
            restored.close()
        with pytest.raises(FileExistsError):
            backup_database(original, saved)
        assert saved.exists()
        with pytest.raises(ValueError, match="missing"):
            backup_database(tmp_path / "missing", tmp_path / "new")
    finally:
        store.close()


def test_bad_backup_cleans_only_new_destination(tmp_path: Path) -> None:
    source = tmp_path / "invalid"
    destination = tmp_path / "backup"
    source.write_text("not sqlite", encoding="utf-8")
    with pytest.raises(sqlite3.DatabaseError):
        backup_database(source, destination)
    assert source.exists()
    assert not destination.exists()


def test_service_security_contract() -> None:
    unit = (Path(__file__).parents[1] / "deploy/pitboss-admin.service").read_text()
    for setting in (
        "User=pitboss-admin",
        "Restart=on-failure",
        "UMask=0077",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "NoNewPrivileges=true",
        "PITBOSS_MANAGED=true",
        "TimeoutStopSec=45",
        "AF_UNIX",
    ):
        assert setting in unit
    assert "ExecStart=/opt/pitboss-admin/current/venv/bin/pitboss-api" in unit


def test_interactive_bootstrap_shows_token_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    terminal = Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    database = tmp_path / "state.sqlite3"
    bootstrap(database)
    token = terminal.getvalue().splitlines()[-1]
    store = AdministrativeStore(database)
    try:
        assert AdministratorTokens(store).verify(token)
    finally:
        store.close()
    bootstrap(database)
    assert terminal.getvalue().count(token) == 1
    assert b"shown only once" not in database.read_bytes()
    assert token.encode() not in database.read_bytes()


def test_offline_cli_backup_and_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "state.sqlite3"
    store = AdministrativeStore(database)
    store.close()
    for action, extra in (("validate", []), ("backup", [str(tmp_path / "saved.sqlite3")])):
        monkeypatch.setattr(sys, "argv", ["pitboss-state", action, str(database), *extra])
        main()
    assert (tmp_path / "saved.sqlite3").exists()
    monkeypatch.setattr(sys, "argv", ["pitboss-state", "backup", str(database)])
    with pytest.raises(SystemExit):
        main()
