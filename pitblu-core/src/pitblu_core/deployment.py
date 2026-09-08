"""Offline administrative state operations for native deployment."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from pitblu_core.auth import AdministratorTokens
from pitblu_core.configuration import ConfigurationManager
from pitblu_core.storage import AdministrativeStore


def startup_configuration(
    store: AdministrativeStore,
    environment: Mapping[str, str],
) -> ConfigurationManager:
    filename = environment.get("PITBLU_CONFIG_FILE")
    if filename is not None and not Path(filename).is_file():
        raise ValueError("configured startup file is missing")
    config = ConfigurationManager(
        store,
        yaml_path=Path(filename) if filename else None,
        environ=environment,
    )
    if environment.get("PITBLU_MANAGED") == "true":
        if config.config.auth.mode != "token":
            raise ValueError("managed service requires token authentication")
        if not AdministratorTokens(store).status().configured:
            raise ValueError("bootstrap an administrator token before starting the managed service")
    return config


def backup_database(source: Path, destination: Path) -> None:
    """Create a new protected consistent backup, never overwrite an existing path."""
    if not source.is_file():
        raise ValueError("source database is missing")
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with (
            closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader,
            closing(sqlite3.connect(destination)) as writer,
        ):
            reader.backup(writer)
            if writer.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("database integrity check failed")
    except BaseException:
        destination.unlink()
        raise


def bootstrap(database: Path) -> None:
    if not sys.stdout.isatty():
        raise ValueError("token bootstrap requires a terminal; never redirect it to a log")
    store = AdministrativeStore(database)
    try:
        tokens = AdministratorTokens(store)
        if tokens.status().configured:
            print("Administrator token already configured; unchanged.")
        else:
            token = tokens.bootstrap()
            print("Save this administrator token securely; it is shown only once:")
            print(token)
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bootstrap", "backup", "validate"))
    parser.add_argument("database", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "bootstrap":
        bootstrap(args.database)
    elif args.action == "backup":
        if args.destination is None:
            parser.error("backup requires a new destination path")
        backup_database(args.database, args.destination)
        print("Database backup verified.")
    else:
        if not args.database.is_file():
            parser.error("validation requires an existing database")
        store = AdministrativeStore(args.database)
        try:
            startup_configuration(store, os.environ)
        except Exception:
            raise SystemExit(
                "Managed startup configuration is invalid; no values are displayed."
            ) from None
        finally:
            store.close()
        print("Managed startup configuration validated.")
