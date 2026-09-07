"""Typed configuration with layered sources and transactional overrides."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from pitboss_admin.storage import AdministrativeStore


class ConfigurationValueError(ValueError):
    pass


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerConfig(_Section):
    bind: Literal["127.0.0.1", "0.0.0.0"] = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=list)


class AuthConfig(_Section):
    mode: Literal["disabled", "token"] = "disabled"


class BluetoothConfig(_Section):
    scan_duration: float = Field(5, gt=0, le=60)
    missing_scan_interval: float = Field(15, gt=0, le=3600)
    connected_scan_interval: float = Field(60, gt=0, le=3600)
    connect_timeout: float = Field(10, gt=0, le=120)
    initialise_timeout: float = Field(15, gt=0, le=120)
    read_timeout: float = Field(5, gt=0, le=60)


class PollingConfig(_Section):
    probe_interval: float = Field(5, gt=0, le=300)
    battery_interval: float = Field(300, gt=0, le=3600)
    stale_after: float = Field(15, gt=0, le=3600)
    degraded_after_failures: int = Field(3, ge=1, le=100)
    forced_reconnect_after: float = Field(30, gt=0, le=3600)
    availability_heartbeat: float = Field(60, gt=0, le=3600)
    stable_backoff_reset: float = Field(60, gt=0, le=3600)


class MqttConfig(_Section):
    enabled: bool = False
    host: str = Field("127.0.0.1", min_length=1, max_length=253)
    port: int = Field(1883, ge=1, le=65535)
    tls: bool = False
    username: str | None = Field(None, max_length=128)
    base_topic: str = Field("pitboss", min_length=1, max_length=128, pattern=r"^[^+#\x00]+$")
    qos: Literal[1] = 1


class SimulationConfig(_Section):
    enabled: bool = False
    probe_count: int = Field(4, ge=1, le=4)


class AppConfig(_Section):
    server: ServerConfig = Field(default_factory=lambda: ServerConfig())
    auth: AuthConfig = Field(default_factory=lambda: AuthConfig())
    bluetooth: BluetoothConfig = Field(default_factory=lambda: BluetoothConfig())
    polling: PollingConfig = Field(default_factory=lambda: PollingConfig())
    mqtt: MqttConfig = Field(default_factory=lambda: MqttConfig())
    simulation: SimulationConfig = Field(default_factory=lambda: SimulationConfig())

    @model_validator(mode="after")
    def secure_exposure(self) -> AppConfig:
        if self.server.bind != "127.0.0.1" and self.auth.mode != "token":
            raise ValueError("non-loopback binding requires token authentication")
        return self


_DESCRIPTIONS = {
    "server.bind": "API listen address; non-loopback requires token authentication.",
    "server.port": "API TCP port.",
    "server.cors_origins": "Explicit browser origins; empty disables CORS.",
    "auth.mode": "Bearer-token authentication mode.",
    "bluetooth.scan_duration": "Duration of each BLE scan in seconds.",
    "bluetooth.missing_scan_interval": "Scan interval while a device is missing.",
    "bluetooth.connected_scan_interval": "Background scan interval while connected.",
    "bluetooth.connect_timeout": "BLE connection deadline in seconds.",
    "bluetooth.initialise_timeout": "Weber initialisation deadline in seconds.",
    "bluetooth.read_timeout": "Individual GATT read deadline in seconds.",
    "polling.probe_interval": "Probe polling interval in seconds.",
    "polling.battery_interval": "Battery polling interval in seconds.",
    "polling.stale_after": "Reading stale threshold in seconds.",
    "polling.degraded_after_failures": "Failed cycles before degraded state.",
    "polling.forced_reconnect_after": "Reconnect threshold without valid readings.",
    "polling.availability_heartbeat": "Availability heartbeat interval in seconds.",
    "polling.stable_backoff_reset": "Stable duration before resetting backoff.",
    "mqtt.enabled": "Enable MQTT telemetry publishing.",
    "mqtt.host": "MQTT broker host.",
    "mqtt.port": "MQTT broker port.",
    "mqtt.tls": "Use TLS for MQTT.",
    "mqtt.username": "MQTT user name; password is a write-only secret.",
    "mqtt.base_topic": "MQTT base topic.",
    "mqtt.qos": "MQTT quality of service for version-one publications.",
    "simulation.enabled": "Use the simulated adapter; disabled by default.",
    "simulation.probe_count": "Number of simulated probes.",
}

_LIMITS: dict[str, tuple[float | int | None, float | int | None]] = {
    "server.port": (1, 65535),
    "bluetooth.scan_duration": (0, 60),
    "bluetooth.missing_scan_interval": (0, 3600),
    "bluetooth.connected_scan_interval": (0, 3600),
    "bluetooth.connect_timeout": (0, 120),
    "bluetooth.initialise_timeout": (0, 120),
    "bluetooth.read_timeout": (0, 60),
    "polling.probe_interval": (0, 300),
    "polling.battery_interval": (0, 3600),
    "polling.stale_after": (0, 3600),
    "polling.degraded_after_failures": (1, 100),
    "polling.forced_reconnect_after": (0, 3600),
    "polling.availability_heartbeat": (0, 3600),
    "polling.stable_backoff_reset": (0, 3600),
    "mqtt.port": (1, 65535),
    "simulation.probe_count": (1, 4),
}

_ALLOWED: dict[str, list[object]] = {
    "server.bind": ["127.0.0.1", "0.0.0.0"],
    "auth.mode": ["disabled", "token"],
    "mqtt.qos": [1],
}


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, Mapping):
            flattened.update(_flatten(item, path))
        else:
            flattened[path] = item
    return flattened


def _inflate(values: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, value in values.items():
        target = result
        parts = path.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return result


class ConfigurationManager:
    def __init__(
        self,
        store: AdministrativeStore,
        *,
        yaml_path: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._store = store
        defaults = _flatten(AppConfig().model_dump())
        self._values = defaults.copy()
        self._sources = dict.fromkeys(defaults, "default")
        if yaml_path is not None and yaml_path.exists():
            loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, Mapping):
                raise ConfigurationValueError("configuration YAML must contain an object")
            self._apply_layer(_flatten(loaded), "yaml")
        environment = os.environ if environ is None else environ
        env_values = {
            key.removeprefix("PITBOSS_").lower().replace("__", "."): yaml.safe_load(value)
            for key, value in environment.items()
            if key.startswith("PITBOSS_")
            and key not in {"PITBOSS_DATABASE_PATH", "PITBOSS_CONFIG_FILE", "PITBOSS_MANAGED"}
        }
        self._apply_layer(env_values, "environment")
        self._version, persisted = store.config_state()
        self._persisted = {key: json.loads(value) for key, value in persisted.items()}
        self._apply_layer(self._persisted, "persisted_override")
        self._config = AppConfig.model_validate(_inflate(self._values))

    def _apply_layer(self, values: Mapping[str, Any], source: str) -> None:
        unknown = set(values) - set(self._values)
        if unknown:
            raise ConfigurationValueError(f"unknown configuration setting: {sorted(unknown)[0]}")
        self._values.update(values)
        self._sources.update(dict.fromkeys(values, source))

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def version(self) -> int:
        return self._version

    def describe(self) -> dict[str, Any]:
        defaults = _flatten(AppConfig().model_dump())
        return {
            "version": self._version,
            "settings": {
                key: {
                    "value": value,
                    "source": self._sources[key],
                    "type": type(defaults[key]).__name__,
                    "description": _DESCRIPTIONS[key],
                    "default": defaults[key],
                    "minimum": _LIMITS.get(key, (None, None))[0],
                    "maximum": _LIMITS.get(key, (None, None))[1],
                    "allowed": _ALLOWED.get(key),
                    "editable": True,
                    "sensitive": False,
                    "restartRequired": True,
                }
                for key, value in self._values.items()
            },
        }

    def validate_patch(self, values: Mapping[str, Any]) -> AppConfig:
        unknown = set(values) - set(self._values)
        if unknown:
            raise ConfigurationValueError(f"unknown configuration setting: {sorted(unknown)[0]}")
        candidate = self._values | dict(values)
        return AppConfig.model_validate(_inflate(candidate))

    def update(self, values: Mapping[str, Any], expected_version: int) -> AppConfig:
        candidate = self.validate_patch(values)
        persisted = self._persisted | dict(values)
        encoded = {key: json.dumps(value) for key, value in persisted.items()}
        self._version = self._store.replace_config(encoded, expected_version)
        self._persisted = persisted
        self._values.update(values)
        self._sources.update(dict.fromkeys(values, "persisted_override"))
        self._config = candidate
        return candidate
