from __future__ import annotations

from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from pitblu_core.api_client import ApiError, ApiResponse
from pitblu_core.install_cli import InstallApplication, build_parser, execute_foreground
from pitblu_core.system_checks import DEPENDENCIES, CommandResult
from pitblu_core.terminal import CheckResult, ResultLevel, Terminal


class TtyBuffer(StringIO):
    def isatty(self) -> bool:
        return True


class FakeRunner:
    def __init__(self, responses: list[CommandResult]) -> None:
        self.responses = iter(responses)
        self.commands: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 15) -> CommandResult:
        self.commands.append(arguments)
        return next(self.responses)


def _terminal(answers: list[str]) -> tuple[Terminal, TtyBuffer]:
    output = TtyBuffer()
    responses = iter(answers)
    return (
        Terminal(
            input_stream=output,
            output_stream=output,
            environ={"NO_COLOR": "1"},
            input_fn=lambda _prompt: next(responses),
        ),
        output,
    )


def _dependency_responses(*, missing: str | None = None) -> list[CommandResult]:
    return [
        CommandResult(1)
        if dependency.package == missing
        else CommandResult(0, "install ok installed")
        for dependency in DEPENDENCIES
    ]


def test_dependency_install_defaults_to_no(tmp_path: Path, monkeypatch: Any) -> None:
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "manage.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    terminal, output = _terminal([""])
    foreground: list[tuple[str, ...]] = []
    runner = FakeRunner([*_dependency_responses(missing="bluez"), CommandResult(1)])
    monkeypatch.setattr(
        "pitblu_core.install_cli.platform_checks",
        lambda: [CheckResult(ResultLevel.PASS, "Platform", "supported")],
    )

    def record_foreground(command: Sequence[str]) -> int:
        foreground.append(tuple(command))
        return 0

    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        command_runner=runner,  # type: ignore[arg-type]
        foreground=record_foreground,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.deploy("install") == 1
    assert foreground == []
    assert "No deployment changes were made" in output.getvalue()


def test_fresh_install_delegates_fixed_commands_and_warns_about_one_time_token(
    tmp_path: Path, monkeypatch: Any
) -> None:
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    script = deploy / "manage.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    terminal, output = _terminal(["", "n"])
    commands: list[tuple[str, ...]] = []
    runner = FakeRunner(
        [
            *_dependency_responses(),
            CommandResult(0, "Powered: yes"),
            CommandResult(0, "active"),
            CommandResult(0, "Powered: yes"),
            CommandResult(0, "1.0.0"),
        ]
    )
    monkeypatch.setattr("pitblu_core.install_cli.platform_checks", lambda: [])
    monkeypatch.setattr(
        "pitblu_core.install_cli.ApiClient",
        lambda: type(
            "HealthyClient",
            (),
            {"wait_for_health": lambda self: ApiResponse(200, {"status": "ok"})},
        )(),
    )

    def record_command(command: Sequence[str]) -> int:
        commands.append(tuple(command))
        return 0

    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        command_runner=runner,  # type: ignore[arg-type]
        foreground=record_command,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.deploy("install") == 0
    assert commands == [
        ("sudo", "bash", str(script), "install"),
        ("sudo", "systemctl", "enable", "--now", "pitblu-core.service"),
    ]
    assert "shown once" in output.getvalue()
    assert "secure password manager" in output.getvalue()


def test_installer_refuses_running_whole_workflow_as_root(tmp_path: Path) -> None:
    terminal, output = _terminal([])
    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        effective_uid=lambda: 0,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
    )

    assert app.deploy("install") == 1
    assert "normal user" in output.getvalue()


def test_parser_exposes_approved_install_commands() -> None:
    parser = build_parser()
    for command in ("check", "install", "upgrade"):
        assert parser.parse_args([command]).command == command


def test_deployment_script_manages_launcher_lifecycle() -> None:
    script = (Path(__file__).parents[1] / "deploy/manage.sh").read_text(encoding="utf-8")

    assert 'install_launcher_link "$install_launcher"' in script
    assert 'install_launcher_link "$config_launcher"' in script
    assert "remove_config_launcher" in script
    uninstall = script.rsplit("    uninstall)", 1)[1].split(";;", 1)[0]
    assert "remove_config_launcher" in uninstall
    assert "install_launcher" not in uninstall


def test_guided_detects_existing_install_and_can_cancel(tmp_path: Path) -> None:
    current = tmp_path / "opt/current"
    current.mkdir(parents=True)
    terminal, output = _terminal([""])
    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.guided() == 0
    assert "existing deployment" in output.getvalue()


def test_dependency_install_is_rechecked_before_deployment(
    tmp_path: Path, monkeypatch: Any
) -> None:
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    script = deploy / "manage.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    terminal, output = _terminal(["y"])
    runner = FakeRunner(
        [
            *_dependency_responses(missing="bluez"),
            CommandResult(1),
            *_dependency_responses(),
        ]
    )
    commands: list[tuple[str, ...]] = []

    def foreground(command: Sequence[str]) -> int:
        commands.append(tuple(command))
        return 1 if command[1:3] == ("bash", str(script)) else 0

    monkeypatch.setattr("pitblu_core.install_cli.platform_checks", lambda: [])
    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        command_runner=runner,  # type: ignore[arg-type]
        foreground=foreground,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.deploy("install") == 1
    assert commands[:2] == [
        ("sudo", "apt-get", "update"),
        ("sudo", "apt-get", "install", "--yes", "bluez"),
    ]
    assert commands[2] == ("sudo", "bash", str(script), "install")
    assert "Dependency recheck" in output.getvalue()


def test_missing_source_checkout_has_clear_error(tmp_path: Path) -> None:
    terminal, _output = _terminal([])
    app = InstallApplication(
        source_root=None,
        terminal=terminal,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    with pytest.raises(ApiError, match="fresh GitHub checkout"):
        app._deployment_script()


def test_install_and_upgrade_are_not_interchangeable(tmp_path: Path) -> None:
    terminal, output = _terminal([])
    app = InstallApplication(
        source_root=tmp_path,
        terminal=terminal,
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.deploy("upgrade") == 1
    assert "use the install command instead" in output.getvalue()


def test_foreground_executor_reports_missing_command() -> None:
    assert execute_foreground(("pitblu-command-that-does-not-exist",)) == 127


def test_noninteractive_guided_mode_explains_subcommands(tmp_path: Path) -> None:
    output = StringIO()
    app = InstallApplication(
        source_root=tmp_path,
        terminal=Terminal(output_stream=output),
        deployment_root=tmp_path / "opt",
        unit_path=tmp_path / "unit",
        effective_uid=lambda: 1000,
    )

    assert app.guided() == 2
    assert "check, install, or upgrade" in output.getvalue()
