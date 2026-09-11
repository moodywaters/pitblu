from __future__ import annotations

from io import StringIO
from typing import Any

from pitblu_core.api_client import ApiError, ApiResponse
from pitblu_core.config_cli import ConfigApplication, build_parser
from pitblu_core.system_checks import CommandResult
from pitblu_core.terminal import Terminal


class TtyBuffer(StringIO):
    def isatty(self) -> bool:
        return True


class FakeRunner:
    def __init__(self) -> None:
        self.responses = iter(
            [CommandResult(0, "active"), CommandResult(0, "Controller\n Powered: yes")]
        )

    def run(self, _arguments: object, *, timeout: float = 15) -> CommandResult:
        return next(self.responses)


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses

    def get(self, path: str, *, authenticated: bool = True) -> ApiResponse:
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return ApiResponse(200, value)

    def device_path(self, device_id: str, suffix: str = "") -> str:
        return f"/api/v1/devices/{device_id}{suffix}"


def _application(
    responses: dict[str, Any], *, token: str = "token"
) -> tuple[ConfigApplication, TtyBuffer]:
    output = TtyBuffer()
    terminal = Terminal(
        input_stream=output,
        output_stream=output,
        environ={"NO_COLOR": "1"},
        secret_fn=lambda _prompt: token,
    )
    client = FakeClient(responses)
    app = ConfigApplication(
        terminal=terminal,
        client_factory=lambda **_kwargs: client,  # type: ignore[arg-type]
        runner=FakeRunner(),  # type: ignore[arg-type]
    )
    return app, output


def test_check_reports_runtime_devices_and_readings(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "pitblu_core.config_cli.platform_checks",
        lambda: [],
    )
    app, output = _application(
        {
            "/health": {"status": "ok"},
            "/ready": {"status": "ready"},
            "/api/v1/status": {
                "status": "ok",
                "version": "1.0.0",
                "mqtt": {"state": "disabled"},
                "host": {"clockSynchronized": True},
            },
            "/api/v1/devices": [
                {
                    "deviceId": "igrill-one",
                    "name": "iGrill\x1b",
                    "friendlyName": None,
                    "desiredState": "connected",
                    "observedState": "polling",
                }
            ],
            "/api/v1/devices/igrill-one/probes": [{"fresh": True}, {"fresh": True}],
            "/api/v1/devices/igrill-one/battery": {"fresh": True, "percentage": 40},
        }
    )

    assert app.check(port=8080) == 0
    report = output.getvalue()
    assert "PASS  Runtime: version 1.0.0; status ok" in report
    assert "PASS  Probes iGrill?: 2 fresh reading(s)" in report
    assert "PASS  Battery iGrill?: 40%" in report
    assert "token" not in report


def test_check_reports_authentication_failure(monkeypatch: Any) -> None:
    monkeypatch.setattr("pitblu_core.config_cli.platform_checks", lambda: [])
    app, output = _application(
        {"/health": {"status": "ok"}, "/ready": ApiError("Token rejected", status=401)}
    )

    assert app.check(port=8080) == 1
    assert "FAIL  Authentication: Token rejected" in output.getvalue()


def test_check_requires_tty_for_token(monkeypatch: Any) -> None:
    monkeypatch.setattr("pitblu_core.config_cli.platform_checks", lambda: [])
    output = StringIO()
    app = ConfigApplication(
        terminal=Terminal(output_stream=output),
        client_factory=lambda **_kwargs: FakeClient({"/health": {"status": "ok"}}),  # type: ignore[arg-type]
        runner=FakeRunner(),  # type: ignore[arg-type]
    )

    assert app.check(port=8080) == 1
    assert "run this command in a terminal" in output.getvalue()


def test_parser_exposes_approved_commands() -> None:
    parser = build_parser()
    for command in ("check", "show", "igrill", "mqtt", "api", "restart"):
        assert parser.parse_args([command]).command == command
