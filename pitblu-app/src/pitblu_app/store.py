from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from pitblu_app.models import DomainError

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS cooks (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL,
 anticipated_serve_at TEXT, created_at TEXT NOT NULL, started_at TEXT,
 cooking_finished_at TEXT, rest_started_at TEXT, served_at TEXT, closed_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_cook ON cooks((1))
 WHERE state IN ('active','cooking_finished','resting','served');
CREATE TABLE IF NOT EXISTS cookers (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL REFERENCES cooks(id), name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS food_items (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL REFERENCES cooks(id), name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL REFERENCES cooks(id), label TEXT NOT NULL,
 kind TEXT NOT NULL, cooker_id TEXT REFERENCES cookers(id), food_item_id TEXT REFERENCES food_items(id),
 target_temperature_c REAL, approaching_margin_c REAL NOT NULL DEFAULT 3,
 range_min_c REAL, range_max_c REAL, range_persistence_seconds INTEGER NOT NULL DEFAULT 120,
 current_temperature_c REAL, current_observed_at TEXT, available INTEGER NOT NULL DEFAULT 0,
 out_of_range_since TEXT);
CREATE TABLE IF NOT EXISTS assignments (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL REFERENCES cooks(id), measurement_id TEXT NOT NULL REFERENCES measurements(id),
 core_device_id TEXT NOT NULL, probe_channel INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS active_source_assignment ON assignments(core_device_id, probe_channel)
 WHERE ended_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS active_measurement_assignment ON assignments(measurement_id)
 WHERE ended_at IS NULL;
CREATE TABLE IF NOT EXISTS temperature_readings (
 id INTEGER PRIMARY KEY AUTOINCREMENT, cook_id TEXT NOT NULL, measurement_id TEXT,
 assignment_id TEXT, core_device_id TEXT NOT NULL, probe_channel INTEGER NOT NULL,
 temperature_c REAL, observed_at TEXT NOT NULL, received_at TEXT NOT NULL, available INTEGER NOT NULL,
 event_id TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS readings_cook_time ON temperature_readings(cook_id, observed_at);
CREATE TABLE IF NOT EXISTS cook_events (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL REFERENCES cooks(id), type TEXT NOT NULL,
 note TEXT, occurred_at TEXT NOT NULL, idempotency_key TEXT, UNIQUE(cook_id,idempotency_key));
CREATE TABLE IF NOT EXISTS alerts (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, measurement_id TEXT, type TEXT NOT NULL,
 severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, action TEXT,
 current_temperature_c REAL, threshold_json TEXT, triggered_at TEXT NOT NULL,
 acknowledged_at TEXT, resolved_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_alert_condition
 ON alerts(measurement_id,type) WHERE status IN ('active','acknowledged');
CREATE TABLE IF NOT EXISTS follower_shares (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL, revoked_at TEXT, expires_at TEXT);
"""

SCHEMA_VERSION = 4

ALERT_HISTORY_MIGRATION = """
ALTER TABLE alerts RENAME TO alerts_legacy;
CREATE TABLE alerts (
 id TEXT PRIMARY KEY, cook_id TEXT NOT NULL, measurement_id TEXT, type TEXT NOT NULL,
 severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, action TEXT,
 current_temperature_c REAL, threshold_json TEXT, triggered_at TEXT NOT NULL,
 acknowledged_at TEXT, resolved_at TEXT);
INSERT INTO alerts (
 id,cook_id,measurement_id,type,severity,status,message,action,current_temperature_c,
 threshold_json,triggered_at,acknowledged_at,resolved_at)
SELECT id,cook_id,measurement_id,type,severity,
 CASE WHEN status IN ('active','acknowledged') AND id != (
   SELECT newest.id FROM alerts_legacy newest
   WHERE newest.measurement_id IS alerts_legacy.measurement_id
     AND newest.type=alerts_legacy.type
     AND newest.status IN ('active','acknowledged')
   ORDER BY newest.triggered_at DESC,newest.id DESC LIMIT 1
 ) THEN 'resolved' ELSE status END,
 message,action,current_temperature_c,threshold_json,triggered_at,acknowledged_at,
 CASE WHEN status IN ('active','acknowledged') AND id != (
   SELECT newest.id FROM alerts_legacy newest
   WHERE newest.measurement_id IS alerts_legacy.measurement_id
     AND newest.type=alerts_legacy.type
     AND newest.status IN ('active','acknowledged')
   ORDER BY newest.triggered_at DESC,newest.id DESC LIMIT 1
 ) THEN COALESCE(resolved_at,triggered_at) ELSE resolved_at END
FROM alerts_legacy;
DROP TABLE alerts_legacy;
CREATE UNIQUE INDEX one_live_alert_condition
 ON alerts(measurement_id,type) WHERE status IN ('active','acknowledged');
"""

DEFAULT_FOLLOWER_SHARE_MIGRATION = """
ALTER TABLE follower_shares ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;
ALTER TABLE follower_shares ADD COLUMN token_nonce TEXT;
CREATE UNIQUE INDEX active_default_share_per_cook ON follower_shares(cook_id)
 WHERE is_default=1 AND revoked_at IS NULL AND expires_at IS NULL;
"""

REUSABLE_COOKERS_MIGRATION = """
CREATE TABLE cooker_profiles (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT, created_at TEXT NOT NULL);
ALTER TABLE cookers ADD COLUMN profile_id TEXT REFERENCES cooker_profiles(id);
INSERT INTO cooker_profiles(id,name,created_at)
 SELECT 'cooker_profile_' || lower(hex(randomblob(16))), name, datetime('now')
 FROM cookers GROUP BY name;
UPDATE cookers SET profile_id=(
 SELECT id FROM cooker_profiles WHERE cooker_profiles.name=cookers.name);
"""


class Store:
    def __init__(self, path: str | Path = "pitblu-app.sqlite3") -> None:
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            self._migrate()
        except Exception:
            self.connection.close()
            raise

    def _migrate(self) -> None:
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema {version} is newer than supported {SCHEMA_VERSION}"
            )
        if version < 1:
            self._apply_migration(SCHEMA, 1)
            version = 1
        if version < 2:
            self._apply_migration(ALERT_HISTORY_MIGRATION, 2, foreign_keys_off=True)
            version = 2
        if version < 3:
            self._apply_migration(DEFAULT_FOLLOWER_SHARE_MIGRATION, 3)
            version = 3
        if version < 4:
            self._apply_migration(REUSABLE_COOKERS_MIGRATION, 4)

    def _apply_migration(
        self, script: str, version: int, *, foreign_keys_off: bool = False
    ) -> None:
        if foreign_keys_off:
            self.connection.execute("PRAGMA foreign_keys=OFF")
        try:
            self.connection.executescript(
                f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version={version};\nCOMMIT;"
            )
        except Exception:
            self.connection.rollback()
            raise
        finally:
            self.connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def ident(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    def one(self, sql: str, values: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        row = self.connection.execute(sql, values).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute(sql, values).fetchall()]

    def require(self, table: str, item_id: str) -> dict[str, Any]:
        if table not in {
            "cooks",
            "cookers",
            "cooker_profiles",
            "food_items",
            "measurements",
            "alerts",
        }:
            raise ValueError("invalid table")
        item = self.one(f"SELECT * FROM {table} WHERE id=?", (item_id,))
        if item is None:
            raise DomainError(f"{table.rstrip('s')} not found", 404, "not_found")
        return item

    def close(self) -> None:
        self.connection.close()


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "cook_id": "cookId",
        "anticipated_serve_at": "anticipatedServeAt",
        "created_at": "createdAt",
        "started_at": "startedAt",
        "cooking_finished_at": "cookingFinishedAt",
        "rest_started_at": "restStartedAt",
        "served_at": "servedAt",
        "closed_at": "closedAt",
        "cooker_id": "cookerId",
        "profile_id": "profileId",
        "food_item_id": "foodItemId",
        "target_temperature_c": "targetTemperatureC",
        "temperature_c": "temperatureC",
        "approaching_margin_c": "approachingMarginC",
        "range_min_c": "rangeMinC",
        "range_max_c": "rangeMaxC",
        "range_persistence_seconds": "rangePersistenceSeconds",
        "current_temperature_c": "currentTemperatureC",
        "current_observed_at": "currentObservedAt",
        "measurement_id": "measurementId",
        "core_device_id": "coreDeviceId",
        "probe_channel": "probeChannel",
        "ended_at": "endedAt",
        "occurred_at": "occurredAt",
        "triggered_at": "triggeredAt",
        "acknowledged_at": "acknowledgedAt",
        "resolved_at": "resolvedAt",
        "received_at": "receivedAt",
        "observed_at": "observedAt",
        "is_default": "isDefault",
    }
    result = {aliases.get(key, key): value for key, value in row.items()}
    for key in ("available",):
        if key in result:
            result[key] = bool(result[key])
    if "threshold_json" in result:
        result["threshold"] = json.loads(result.pop("threshold_json") or "{}")
    return result
