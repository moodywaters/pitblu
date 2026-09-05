"""SQLite persistence for administrative state only."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from threading import RLock


class AdministrativeStore:
    """Small transactional store that never contains telemetry history."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = RLock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialise()

    def _initialise(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO metadata(key, value) VALUES ('config_version', '1');
                CREATE TABLE IF NOT EXISTS config_overrides (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS secrets (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS administrator_auth (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    salt BLOB NOT NULL,
                    digest BLOB NOT NULL,
                    changed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    discovery_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    friendly_name TEXT,
                    model TEXT NOT NULL,
                    auto_reconnect INTEGER NOT NULL,
                    desired_state TEXT NOT NULL,
                    observed_state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    device_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_code TEXT
                );
                CREATE TABLE IF NOT EXISTS operational_events (
                    ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL
                );
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(devices)")}
            if "identity" not in columns:
                connection.execute("ALTER TABLE devices ADD COLUMN identity TEXT")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except BaseException:
                self._connection.rollback()
                raise

    def config_state(self) -> tuple[int, dict[str, str]]:
        with self._lock:
            version = int(
                self._connection.execute(
                    "SELECT value FROM metadata WHERE key = 'config_version'"
                ).fetchone()["value"]
            )
            rows = self._connection.execute(
                "SELECT key, value_json FROM config_overrides"
            ).fetchall()
        return version, {row["key"]: row["value_json"] for row in rows}

    def replace_config(self, values: Mapping[str, str], expected_version: int) -> int:
        with self.transaction() as connection:
            current = int(
                connection.execute(
                    "SELECT value FROM metadata WHERE key = 'config_version'"
                ).fetchone()["value"]
            )
            if current != expected_version:
                raise VersionConflictError(current)
            connection.execute("DELETE FROM config_overrides")
            connection.executemany(
                "INSERT INTO config_overrides(key, value_json) VALUES (?, ?)", values.items()
            )
            new_version = current + 1
            connection.execute(
                "UPDATE metadata SET value = ? WHERE key = 'config_version'", (str(new_version),)
            )
        return new_version

    def put_secret(self, name: str, value: str, changed_at: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO secrets(name, value, changed_at) VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value,
                changed_at = excluded.changed_at""",
                (name, value, changed_at),
            )

    def secret_status(self, name: str) -> tuple[bool, str | None]:
        with self._lock:
            row = self._connection.execute(
                "SELECT changed_at FROM secrets WHERE name = ?", (name,)
            ).fetchone()
        return (False, None) if row is None else (True, str(row["changed_at"]))

    def get_secret(self, name: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM secrets WHERE name = ?", (name,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def delete_secret(self, name: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM secrets WHERE name = ?", (name,))
        return cursor.rowcount > 0

    def auth_record(self) -> tuple[bytes, bytes, str] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT salt, digest, changed_at FROM administrator_auth WHERE singleton = 1"
            ).fetchone()
        if row is None:
            return None
        return bytes(row["salt"]), bytes(row["digest"]), str(row["changed_at"])

    def set_auth_record(self, salt: bytes, digest: bytes, changed_at: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO administrator_auth(singleton, salt, digest, changed_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET salt = excluded.salt,
                digest = excluded.digest, changed_at = excluded.changed_at""",
                (salt, digest, changed_at),
            )

    def save_device(self, values: Mapping[str, object]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO devices(
                    device_id, discovery_id, name, friendly_name, model, auto_reconnect,
                    desired_state, observed_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["device_id"],
                    values["discovery_id"],
                    values["name"],
                    values["friendly_name"],
                    values["model"],
                    int(bool(values["auto_reconnect"])),
                    values["desired_state"],
                    values["observed_state"],
                    values["created_at"],
                ),
            )
            connection.execute(
                "UPDATE devices SET identity = ? WHERE device_id = ?",
                (values.get("identity"), values["device_id"]),
            )

    def devices(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM devices ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def update_device(self, device_id: str, values: Mapping[str, object]) -> bool:
        allowed = {
            "friendly_name",
            "auto_reconnect",
            "desired_state",
            "observed_state",
            "identity",
            "discovery_id",
        }
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return self.device(device_id) is not None
        assignments = ", ".join(f"{key} = ?" for key in selected)
        parameters = [
            (1 if bool(value) else 0) if key == "auto_reconnect" else value
            for key, value in selected.items()
        ]
        with self.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE devices SET {assignments} WHERE device_id = ?",
                (*parameters, device_id),
            )
        return cursor.rowcount > 0

    def device(self, device_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM devices WHERE device_id = ?", (device_id,)
            ).fetchone()
        return None if row is None else dict(row)

    def delete_device(self, device_id: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute("DELETE FROM devices WHERE device_id = ?", (device_id,))
        return cursor.rowcount > 0

    def save_operation(self, values: Mapping[str, object]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO operations(
                    operation_id, kind, device_id, status, created_at, updated_at, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(operation_id) DO UPDATE SET status = excluded.status,
                updated_at = excluded.updated_at, error_code = excluded.error_code""",
                (
                    values["operation_id"],
                    values["kind"],
                    values.get("device_id"),
                    values["status"],
                    values["created_at"],
                    values["updated_at"],
                    values.get("error_code"),
                ),
            )
            connection.execute(
                "DELETE FROM operations WHERE status IN ('succeeded','failed') "
                "AND operation_id NOT IN (SELECT operation_id FROM operations "
                "ORDER BY created_at DESC LIMIT 100)"
            )

    def operations(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM operations ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]

    def operation(self, operation_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
        return None if row is None else dict(row)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def interrupt_operations(self, timestamp: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE operations SET status='failed', error_code='interrupted', updated_at=? "
                "WHERE status IN ('queued', 'running')",
                (timestamp,),
            )

    def append_event(self, payload: dict[str, object]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO operational_events(payload) VALUES (?)", (json.dumps(payload),)
            )
            connection.execute(
                "DELETE FROM operational_events WHERE ordinal NOT IN "
                "(SELECT ordinal FROM operational_events ORDER BY ordinal DESC LIMIT 100)"
            )

    def recent_events(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM operational_events ORDER BY ordinal"
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]


class VersionConflictError(RuntimeError):
    def __init__(self, current_version: int) -> None:
        super().__init__("configuration version conflict")
        self.current_version = current_version
