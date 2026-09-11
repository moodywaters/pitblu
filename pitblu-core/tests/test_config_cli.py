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


class RecordingClient(FakeClient):
    def __init__(self, responses: dict[str, Any]) -> None:
        super().__init__(responses)
        self.calls: list[tuple[str, str, Any, str | None]] = []

    def post(self, path: str, body: dict[str, Any] | None = None) -> ApiResponse:
        self.calls.append(("POST", path, body, None))
        return ApiResponse(200, self.responses.get(path, {}))

    def patch(self, path: str, body: dict[str, Any], *, etag: str | None = None) -> ApiResponse:
        self.calls.append(("PATCH", path, body, etag))
        return ApiResponse(200, self.responses.get(path, {}))

    def put(self, path: str, body: dict[str, Any]) -> ApiResponse:
        self.calls.append(("PUT", path, body, None))
        return ApiResponse(200, self.responses.get(path, {}))

    def delete(self, path: str) -> ApiResponse:
        self.calls.append(("DELETE", path, None, None))
        return ApiResponse(200, self.responses.get(path, {}))

    def wait_for_operation(self, operation_id: str) -> ApiResponse:
        self.calls.append(("WAIT", operation_id, None, None))
        return ApiResponse(200, {"status": "succeeded"})


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


def _interactive_application(
    client: RecordingClient, answers: list[str], *, secret: str = "token"
) -> tuple[ConfigApplication, TtyBuffer, FakeRunner]:
    output = TtyBuffer()
    responses = iter(answers)
    terminal = Terminal(
        input_stream=output,
        output_stream=output,
        environ={"NO_COLOR": "1"},
        input_fn=lambda _prompt: next(responses),
        secret_fn=lambda _prompt: secret,
    )
    runner = FakeRunner()
    return (
        ConfigApplication(
            terminal=terminal,
            client_factory=lambda **_kwargs: client,  # type: ignore[arg-type]
            runner=runner,  # type: ignore[arg-type]
        ),
        output,
        runner,
    )


def _config_response() -> ApiResponse:
    values = {
        "mqtt.enabled": False,
        "mqtt.host": "127.0.0.1",
        "mqtt.port": 1883,
        "mqtt.tls": False,
        "mqtt.username": None,
        "mqtt.base_topic": "pitblu",
        "server.bind": "127.0.0.1",
        "server.port": 8080,
        "server.cors_origins": [],
    }
    return ApiResponse(
        200,
        {"settings": {key: {"value": value, "source": "default"} for key, value in values.items()}},
        '"4"',
    )


def test_show_prints_secret_status_not_value() -> None:
    response = _config_response()
    data = dict(response.data)
    data["secrets"] = {"mqtt.password": {"configured": True}}
    client = RecordingClient({"/api/v1/config": data})
    original_get = client.get
    client.get = lambda path, authenticated=True: (  # type: ignore[method-assign]
        ApiResponse(200, data, '"4"') if path == "/api/v1/config" else original_get(path)
    )
    app, output, _runner = _interactive_application(client, [])

    assert app.show(port=8080) == 0
    assert "mqtt.password = configured" in output.getvalue()
    assert "token" not in output.getvalue()


def test_mqtt_validates_then_saves_and_keeps_password_hidden() -> None:
    client = RecordingClient({})
    client.get = lambda _path, authenticated=True: _config_response()  # type: ignore[method-assign]
    # enable, host, port, TLS, username, topic, set password, do not restart
    app, output, _runner = _interactive_application(
        client, ["y", "broker.local", "1884", "y", "pitblu", "bbq", "y", "n"], secret="hidden"
    )

    assert app.mqtt(port=8080) == 0
    assert [call[:2] for call in client.calls] == [
        ("POST", "/api/v1/config/validate"),
        ("PATCH", "/api/v1/config"),
        ("PUT", "/api/v1/config/secrets/mqtt.password"),
    ]
    assert client.calls[1][3] == '"4"'
    assert client.calls[2][2] == {"value": "hidden"}
    assert "hidden" not in output.getvalue()


def test_igrill_scan_registers_opaque_discovery_result() -> None:
    client = RecordingClient(
        {
            "/api/v1/devices": [],
            "/api/v1/scans": {"operationId": "scan-1"},
            "/api/v1/scans/scan-1": {
                "devices": [
                    {
                        "discoveryId": "opaque-id",
                        "name": "iGrill Mini",
                        "model": "v202",
                        "rssi": -45,
                    }
                ]
            },
        }
    )
    app, output, _runner = _interactive_application(client, ["1", "1", "Patio", ""])

    assert app.igrill(port=8080) == 0
    registration = next(call for call in client.calls if call[1] == "/api/v1/devices")
    assert registration[2]["discoveryId"] == "opaque-id"
    assert "Bluetooth address" not in output.getvalue()


def test_restart_uses_fixed_sudo_command_and_defaults_no() -> None:
    client = RecordingClient({})
    app, output, runner = _interactive_application(client, [""])

    assert app.restart() == 0
    assert "Service was not restarted" in output.getvalue()
    # No command was consumed, so the first response is still the service status fixture.
    assert next(runner.responses).stdout == "active"
