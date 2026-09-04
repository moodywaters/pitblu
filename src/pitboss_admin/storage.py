"""SQLite persistence for administrative state only."""

from __future__ import annotations

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
                """
            )

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

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class VersionConflictError(RuntimeError):
    def __init__(self, current_version: int) -> None:
        super().__init__("configuration version conflict")
        self.current_version = current_version
