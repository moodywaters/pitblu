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
            ready = client.get("/ready")
            results.append(
                CheckResult(
                    ResultLevel.PASS if ready.status == 200 else ResultLevel.WARN,
                    "Readiness",
                    self._status_text(ready.data, "unknown"),
                )
            )
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
    if args.command in {None, "check"}:
        return application.check(port=args.port)
    application.terminal.write(f"The {args.command} workflow is not available in this build.")
    return 2
