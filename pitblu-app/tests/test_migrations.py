import sqlite3

import pytest

from pitblu_app.store import SCHEMA_VERSION, Store

LEGACY_ALERTS = """
CREATE TABLE alerts (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, measurement_id TEXT, type TEXT NOT NULL,
 severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, action TEXT,
 current_temperature_c REAL, threshold_json TEXT, triggered_at TEXT NOT NULL,
 acknowledged_at TEXT, resolved_at TEXT, UNIQUE(measurement_id,type,status));
INSERT INTO alerts VALUES
 ('old','cook','measurement','temperature.target_reached','attention','resolved',
 'Reached',NULL,93,'{}','2026-01-01T00:00:00+00:00',NULL,'2026-01-01T00:01:00+00:00');
CREATE TABLE follower_shares (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL, revoked_at TEXT, expires_at TEXT);
CREATE TABLE cookers (id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, name TEXT NOT NULL);
INSERT INTO cookers VALUES ('cooker','cook','WSM');
PRAGMA user_version=1;
"""


def test_fresh_database_reaches_current_schema():
    store = Store(":memory:")
    version = store.connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    store.close()


def test_legacy_alert_constraint_is_migrated(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY_ALERTS)
    connection.close()

    store = Store(path)
    sql = store.connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='alerts'"
    ).fetchone()[0]
    assert "UNIQUE(measurement_id,type,status)" not in sql
    assert store.one("SELECT * FROM alerts WHERE id='old'")["status"] == "resolved"
    share_columns = {
        row[1] for row in store.connection.execute("PRAGMA table_info(follower_shares)")
    }
    assert {"is_default", "token_nonce"} <= share_columns
    assert store.one("SELECT name FROM cooker_profiles WHERE name='WSM'") is not None
    assert store.one("SELECT profile_id FROM cookers WHERE id='cooker'")["profile_id"]
    store.close()


def test_newer_database_is_rejected(tmp_path):
    path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    connection.close()
    with pytest.raises(RuntimeError, match="newer than supported"):
        Store(path)
