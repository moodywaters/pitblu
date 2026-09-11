"""Local-only guided configuration and support CLI."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from typing import Any

from pitblu_core.api_client import ApiClient, ApiError
from pitblu_core.system_checks import CommandRunner, platform_checks, service_checks
from pitblu_core.terminal import CheckResult, ResultLevel, Terminal, safe_text


class ConfigApplication:
    """Coordinate terminal presentation with the local REST API."""

    def __init__(
        self,
        *,
        terminal: Terminal | None = None,
        client_factory: Callable[..., ApiClient] = ApiClient,
        runner: CommandRunner | None = None,
    ) -> None:
        self.terminal = terminal or Terminal()
        self._client_factory = client_factory
        self._runner = runner or CommandRunner()

    def check(self, *, port: int) -> int:
        """Run the canonical, secret-free support check."""

        self.terminal.heading("pitblu-core support check")
        results = [*platform_checks(), *service_checks(self._runner)]
        unauthenticated = self._client_factory(port=port)
        try:
            health = unauthenticated.get("/health", authenticated=False)
            healthy = isinstance(health.data, dict) and health.data.get("status") == "ok"
            results.append(
                CheckResult(
                    ResultLevel.PASS if healthy else ResultLevel.FAIL,
                    "Local API",
                    "health endpoint responded" if healthy else "unexpected health response",
                )
            )
        except ApiError as exc:
            results.append(CheckResult(ResultLevel.FAIL, "Local API", str(exc)))
            return self._finish(results)

        if not self.terminal.interactive:
            results.append(
                CheckResult(
                    ResultLevel.FAIL,
                    "Authentication",
                    "run this command in a terminal so the token can be entered securely",
                )
            )
            return self._finish(results)

        token = self.terminal.secret("Administrator token")
        if not token:
            results.append(CheckResult(ResultLevel.FAIL, "Authentication", "no token supplied"))
            return self._finish(results)
        client = self._client_factory(port=port, token=token)
        try:
            try:
                ready = client.get("/ready")
                results.append(
                    CheckResult(
                        ResultLevel.PASS,
                        "Readiness",
                        self._status_text(ready.data, "unknown"),
                    )
                )
            except ApiError as exc:
                if exc.status != 503:
                    raise
                results.append(CheckResult(ResultLevel.WARN, "Readiness", str(exc)))
            status = client.get("/api/v1/status").data
            if not isinstance(status, dict):
                raise ApiError("The local service returned an invalid status response")
            results.extend(self._status_results(status))
            devices = client.get("/api/v1/devices").data
            results.extend(self._device_results(client, devices))
        except ApiError as exc:
            name = "Authentication" if exc.status == 401 else "Authenticated API"
            results.append(CheckResult(ResultLevel.FAIL, name, str(exc)))
        finally:
            token = ""
        return self._finish(results)

    def show(self, *, port: int) -> int:
        client = self._authenticated_client(port)
        if client is None:
            return 1
        try:
            response = client.get("/api/v1/config")
        except ApiError as exc:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "Configuration", str(exc)))
            return 1
        if not isinstance(response.data, dict) or not isinstance(
            response.data.get("settings"), dict
        ):
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Configuration", "invalid API response")
            )
            return 1
        self.terminal.heading("Effective configuration")
        for name, metadata in sorted(response.data["settings"].items()):
            value = metadata.get("value") if isinstance(metadata, dict) else "unknown"
            source = metadata.get("source") if isinstance(metadata, dict) else "unknown"
            self.terminal.write(f"{name} = {value} ({source})")
        secrets = response.data.get("secrets")
        mqtt_secret = secrets.get("mqtt.password") if isinstance(secrets, dict) else None
        configured = mqtt_secret.get("configured") if isinstance(mqtt_secret, dict) else False
        self.terminal.write(f"mqtt.password = {'configured' if configured else 'not configured'}")
        return 0

    def igrill(self, *, port: int) -> int:
        client = self._mutation_client(port)
        if client is None:
            return 1
        try:
            devices = client.get("/api/v1/devices").data
            if not isinstance(devices, list):
                raise ApiError("The local service returned an invalid device list")
            options = ["Scan for and register an iGrill"]
            valid_devices = [item for item in devices if isinstance(item, dict)]
            options.extend(
                f"Manage {safe_text(item.get('friendlyName') or item.get('name') or 'device')}"
                for item in valid_devices
            )
            selected = self.terminal.choose("iGrill setup", options)
            if selected == 0:
                return self._scan_and_register(client)
            return self._manage_device(client, valid_devices[selected - 1])
        except ApiError as exc:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "iGrill", str(exc)))
            return 1

    def mqtt(self, *, port: int) -> int:
        client = self._mutation_client(port)
        if client is None:
            return 1
        try:
            response, values = self._configuration(client)
            enabled = self.terminal.confirm(
                "Enable MQTT?", default=bool(values.get("mqtt.enabled", False))
            )
            patch: dict[str, Any] = {"mqtt.enabled": enabled}
            if enabled:
                patch.update(
                    {
                        "mqtt.host": self.terminal.ask(
                            "Broker host", default=str(values.get("mqtt.host", "127.0.0.1"))
                        ),
                        "mqtt.port": self._ask_port(
                            "Broker port", int(values.get("mqtt.port", 1883))
                        ),
                        "mqtt.tls": self.terminal.confirm(
                            "Use TLS?", default=bool(values.get("mqtt.tls", False))
                        ),
                        "mqtt.username": self.terminal.ask(
                            "Username (blank for none)",
                            default=str(values.get("mqtt.username") or ""),
                        )
                        or None,
                        "mqtt.base_topic": self.terminal.ask(
                            "Base topic", default=str(values.get("mqtt.base_topic", "pitblu"))
                        ),
                    }
                )
            self._save_configuration(client, response.etag, patch)
            if enabled and self.terminal.confirm("Set or replace the MQTT password?"):
                password = self.terminal.secret("MQTT password")
                if not password:
                    raise ApiError("MQTT password was blank; it was not changed")
                client.put("/api/v1/config/secrets/mqtt.password", {"value": password})
                password = ""
            elif not enabled and self.terminal.confirm("Remove the saved MQTT password?"):
                client.delete("/api/v1/config/secrets/mqtt.password")
            self.terminal.result(
                CheckResult(ResultLevel.PASS, "MQTT", "configuration saved; QoS remains fixed at 1")
            )
            return 0 if self._offer_restart() else 1
        except ApiError as exc:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "MQTT", str(exc)))
            return 1

    def api(self, *, port: int) -> int:
        client = self._mutation_client(port)
        if client is None:
            return 1
        try:
            response, values = self._configuration(client)
            expose = self.terminal.confirm(
                "Listen beyond this Raspberry Pi?",
                default=values.get("server.bind") == "0.0.0.0",
            )
            bind = "0.0.0.0" if expose else "127.0.0.1"
            if expose:
                self.terminal.write(
                    "WARNING: this exposes the API to the local network; token authentication "
                    "remains required."
                )
                if not self.terminal.confirm("Confirm network exposure?"):
                    self.terminal.write("No changes saved.")
                    return 0
            new_port = self._ask_port("API port", int(values.get("server.port", port)))
            current_origins = values.get("server.cors_origins", [])
            origins_text = self.terminal.ask(
                "Allowed browser origins, comma-separated (blank for none)",
                default=", ".join(current_origins if isinstance(current_origins, list) else []),
            )
            origins = [item.strip() for item in origins_text.split(",") if item.strip()]
            self._save_configuration(
                client,
                response.etag,
                {
                    "server.bind": bind,
                    "server.port": new_port,
                    "server.cors_origins": origins,
                    "auth.mode": "token",
                },
            )
            self.terminal.result(
                CheckResult(ResultLevel.PASS, "API", "configuration saved; authentication enabled")
            )
            if new_port != port:
                self.terminal.write(
                    f"After restart, use pitblu-core-config --port {new_port} check."
                )
            return 0 if self._offer_restart() else 1
        except ApiError as exc:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "API", str(exc)))
            return 1

    def restart(self) -> int:
        if not self.terminal.interactive:
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Restart", "run this command in a terminal")
            )
            return 1
        if not self.terminal.confirm("Restart pitblu-core now?"):
            self.terminal.write("Service was not restarted.")
            return 0
        result = self._runner.run(
            ("sudo", "systemctl", "restart", "pitblu-core.service"), timeout=45
        )
        if result.returncode != 0:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "Restart", "systemctl failed"))
            return 1
        self.terminal.result(CheckResult(ResultLevel.PASS, "Restart", "service restarted"))
        return 0

    def menu(self, *, port: int) -> int:
        if not self.terminal.interactive:
            self.terminal.write("Use a subcommand. Start with: pitblu-core-config check")
            return 2
        actions = [
            "Check system",
            "Show configuration",
            "Set up iGrill",
            "Configure MQTT",
            "Configure API",
            "Restart service",
            "Exit",
        ]
        while True:
            selected = self.terminal.choose("pitblu-core configuration", actions)
            if selected == 6:
                return 0
            handlers: list[Callable[[], int]] = [
                lambda: self.check(port=port),
                lambda: self.show(port=port),
                lambda: self.igrill(port=port),
                lambda: self.mqtt(port=port),
                lambda: self.api(port=port),
                self.restart,
            ]
            handlers[selected]()

    def _authenticated_client(self, port: int) -> ApiClient | None:
        if not self.terminal.interactive:
            self.terminal.result(
                CheckResult(
                    ResultLevel.FAIL,
                    "Authentication",
                    "run this command in a terminal so the token can be entered securely",
                )
            )
            return None
        token = self.terminal.secret("Administrator token")
        if not token:
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Authentication", "no token supplied")
            )
            return None
        return self._client_factory(port=port, token=token)

    def _mutation_client(self, port: int) -> ApiClient | None:
        if not self.terminal.interactive:
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Configuration", "interactive terminal required")
            )
            return None
        return self._authenticated_client(port)

    @staticmethod
    def _configuration(client: ApiClient) -> tuple[Any, dict[str, Any]]:
        response = client.get("/api/v1/config")
        if response.etag is None or not isinstance(response.data, dict):
            raise ApiError("The local service returned configuration without an ETag")
        settings = response.data.get("settings")
        if not isinstance(settings, dict):
            raise ApiError("The local service returned invalid configuration")
        values = {
            key: metadata.get("value")
            for key, metadata in settings.items()
            if isinstance(key, str) and isinstance(metadata, dict)
        }
        return response, values

    @staticmethod
    def _save_configuration(client: ApiClient, etag: str | None, values: dict[str, Any]) -> None:
        if etag is None:
            raise ApiError("Configuration ETag is missing")
        client.post("/api/v1/config/validate", {"values": values})
        client.patch("/api/v1/config", {"values": values}, etag=etag)

    def _scan_and_register(self, client: ApiClient) -> int:
        self.terminal.write("Keep the iGrill nearby and awake. Scanning may take a few seconds.")
        operation = client.post("/api/v1/scans", {}).data
        operation_id = operation.get("operationId") if isinstance(operation, dict) else None
        if not isinstance(operation_id, str):
            raise ApiError("The local service did not return a scan operation")
        completed = client.wait_for_operation(operation_id)
        if not isinstance(completed.data, dict) or completed.data.get("status") != "succeeded":
            raise ApiError("The Bluetooth scan failed")
        scan = client.get(f"/api/v1/scans/{operation_id}").data
        candidates = scan.get("devices") if isinstance(scan, dict) else None
        if not isinstance(candidates, list) or not candidates:
            self.terminal.result(CheckResult(ResultLevel.WARN, "Scan", "no supported iGrill found"))
            return 1
        valid = [item for item in candidates if isinstance(item, dict)]
        if not valid:
            raise ApiError("The local service returned invalid scan results")
        labels = []
        for item in valid:
            name = safe_text(item.get("name", "iGrill"))
            model = safe_text(item.get("model", "unknown"))
            rssi = safe_text(item.get("rssi", "unknown"))
            labels.append(f"{name} ({model}, RSSI {rssi})")
        chosen = valid[self.terminal.choose("Select an iGrill", labels)]
        discovery_id = chosen.get("discoveryId")
        if not isinstance(discovery_id, str):
            raise ApiError("The selected discovery result was invalid")
        friendly_name = self.terminal.ask("Friendly name (blank to keep device name)") or None
        connect = self.terminal.confirm("Connect now?", default=True)
        try:
            result = client.post(
                "/api/v1/devices",
                {
                    "discoveryId": discovery_id,
                    "friendlyName": friendly_name,
                    "automaticReconnection": True,
                    "connect": connect,
                },
            ).data
        except ApiError as exc:
            if exc.status == 409 and self.terminal.confirm(
                "That scan result expired. Scan again?", default=True
            ):
                return self._scan_and_register(client)
            raise
        if connect and isinstance(result, dict) and isinstance(result.get("operation"), dict):
            connection_id = result["operation"].get("operationId")
            if isinstance(connection_id, str):
                client.wait_for_operation(connection_id)
        self.terminal.result(CheckResult(ResultLevel.PASS, "iGrill", "registered"))
        return 0

    def _manage_device(self, client: ApiClient, device: dict[str, Any]) -> int:
        device_id = device.get("deviceId")
        if not isinstance(device_id, str):
            raise ApiError("The selected device was invalid")
        actions = [
            "Connect",
            "Disconnect",
            "Reconnect",
            "Rename",
            "Change automatic reconnection",
        ]
        selected = self.terminal.choose("Device action", actions)
        if selected < 3:
            action = ("connect", "disconnect", "reconnect")[selected]
            operation = client.post(client.device_path(device_id, f"/{action}"), {}).data
            operation_id = operation.get("operationId") if isinstance(operation, dict) else None
            if not isinstance(operation_id, str):
                raise ApiError("The local service did not return an operation")
            completed = client.wait_for_operation(operation_id)
            success = (
                isinstance(completed.data, dict) and completed.data.get("status") == "succeeded"
            )
            self.terminal.result(
                CheckResult(ResultLevel.PASS if success else ResultLevel.FAIL, "iGrill", action)
            )
            return 0 if success else 1
        if selected == 3:
            name = self.terminal.ask("Friendly name (blank clears it)") or None
            client.patch(client.device_path(device_id), {"friendlyName": name})
        else:
            enabled = self.terminal.confirm(
                "Reconnect automatically?",
                default=bool(device.get("automaticReconnection", True)),
            )
            client.patch(client.device_path(device_id), {"automaticReconnection": enabled})
        self.terminal.result(CheckResult(ResultLevel.PASS, "iGrill", "device updated"))
        return 0

    def _ask_port(self, prompt: str, default: int) -> int:
        while True:
            value = self.terminal.ask(prompt, default=str(default))
            if value.isdecimal() and 1 <= int(value) <= 65535:
                return int(value)
            self.terminal.write("Enter a port from 1 to 65535.")

    def _offer_restart(self) -> bool:
        if self.terminal.confirm("Restart now to apply the saved settings?"):
            result = self._runner.run(
                ("sudo", "systemctl", "restart", "pitblu-core.service"), timeout=45
            )
            if result.returncode == 0:
                self.terminal.result(CheckResult(ResultLevel.PASS, "Restart", "service restarted"))
            else:
                self.terminal.result(CheckResult(ResultLevel.FAIL, "Restart", "systemctl failed"))
                return False
        return True

    def _status_results(self, status: dict[str, Any]) -> list[CheckResult]:
        version = safe_text(status.get("version", "unknown"))
        overall = status.get("status")
        mqtt = status.get("mqtt")
        mqtt_state = mqtt.get("state") if isinstance(mqtt, dict) else "unknown"
        host = status.get("host")
        clock = host.get("clockSynchronized") if isinstance(host, dict) else None
        return [
            CheckResult(
                ResultLevel.PASS if overall == "ok" else ResultLevel.WARN,
                "Runtime",
                f"version {version}; status {safe_text(overall)}",
            ),
            CheckResult(
                ResultLevel.PASS if mqtt_state in {"connected", "disabled"} else ResultLevel.WARN,
                "MQTT",
                safe_text(mqtt_state),
            ),
            CheckResult(
                ResultLevel.PASS if clock is True else ResultLevel.WARN,
                "Clock",
                "synchronised" if clock is True else "synchronisation not confirmed",
            ),
        ]

    def _device_results(self, client: ApiClient, devices: Any) -> list[CheckResult]:
        if not isinstance(devices, list):
            return [CheckResult(ResultLevel.FAIL, "Devices", "invalid API response")]
        if not devices:
            return [CheckResult(ResultLevel.WARN, "Devices", "none registered")]
        results = [CheckResult(ResultLevel.PASS, "Devices", f"{len(devices)} registered")]
        for item in devices:
            if not isinstance(item, dict) or not isinstance(item.get("deviceId"), str):
                results.append(CheckResult(ResultLevel.FAIL, "Device", "invalid API response"))
                continue
            device_id = item["deviceId"]
            label = item.get("friendlyName") or item.get("name") or device_id
            desired = safe_text(item.get("desiredState", "unknown"))
            observed = safe_text(item.get("observedState", "unknown"))
            level = ResultLevel.PASS if observed in {"connected", "polling"} else ResultLevel.WARN
            results.append(
                CheckResult(
                    level, f"Device {safe_text(label)}", f"desired={desired}, observed={observed}"
                )
            )
            probes = client.get(client.device_path(device_id, "/probes")).data
            fresh = (
                sum(1 for probe in probes if isinstance(probe, dict) and probe.get("fresh") is True)
                if isinstance(probes, list)
                else 0
            )
            results.append(
                CheckResult(
                    ResultLevel.PASS if fresh else ResultLevel.WARN,
                    f"Probes {safe_text(label)}",
                    f"{fresh} fresh reading(s)",
                )
            )
            battery = client.get(client.device_path(device_id, "/battery")).data
            battery_fresh = isinstance(battery, dict) and battery.get("fresh") is True
            percentage = battery.get("percentage") if isinstance(battery, dict) else None
            results.append(
                CheckResult(
                    ResultLevel.PASS if battery_fresh else ResultLevel.WARN,
                    f"Battery {safe_text(label)}",
                    f"{safe_text(percentage)}%" if battery_fresh else "no fresh reading",
                )
            )
        return results

    def _finish(self, results: Sequence[CheckResult]) -> int:
        self.terminal.heading("Summary")
        return 1 if self.terminal.results(results) is ResultLevel.FAIL else 0

    @staticmethod
    def _status_text(data: Any, fallback: str) -> str:
        if isinstance(data, dict):
            return safe_text(data.get("status", fallback))
        return fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pitblu-core-config")
    parser.add_argument("--port", type=int, default=8080, help="local API port (default: 8080)")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("check", help="run the canonical support and diagnostics checks")
    subcommands.add_parser("show", help="show the effective non-secret configuration")
    subcommands.add_parser("igrill", help="scan, register and manage an iGrill")
    subcommands.add_parser("mqtt", help="configure MQTT publishing")
    subcommands.add_parser("api", help="configure API binding and browser origins")
    subcommands.add_parser("restart", help="restart the service after confirmation")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    application = ConfigApplication()
    if args.command is None:
        return application.menu(port=args.port)
    if args.command == "check":
        return application.check(port=args.port)
    if args.command == "show":
        return application.show(port=args.port)
    if args.command == "igrill":
        return application.igrill(port=args.port)
    if args.command == "mqtt":
        return application.mqtt(port=args.port)
    if args.command == "api":
        return application.api(port=args.port)
    if args.command == "restart":
        return application.restart()
    return 2
