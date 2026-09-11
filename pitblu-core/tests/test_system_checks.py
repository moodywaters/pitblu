from __future__ import annotations

from pathlib import Path

from pitblu_core.system_checks import (
    DEPENDENCIES,
    CommandResult,
    CommandRunner,
    dependency_checks,
    platform_checks,
    read_os_release,
    service_checks,
)
from pitblu_core.terminal import ResultLevel


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = iter(results)
        self.commands: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...], *, timeout: float = 15) -> CommandResult:
        self.commands.append(arguments)
        return next(self.results)


def test_supported_raspberry_pi_platform_passes() -> None:
    results = platform_checks(
        system="Linux",
        machine="aarch64",
        python_version=(3, 13),
        os_release={"ID": "raspbian", "VERSION_ID": "13", "PRETTY_NAME": "Pi OS 13"},
    )

    assert [result.level for result in results] == [ResultLevel.PASS] * 3


def test_debian_like_platform_warns_but_bad_architecture_and_python_fail() -> None:
    results = platform_checks(
        system="Linux",
        machine="x86_64",
        python_version=(3, 14),
        os_release={"ID": "ubuntu", "VERSION_ID": "26.04", "PRETTY_NAME": "Ubuntu"},
    )

    assert [result.level for result in results] == [
        ResultLevel.FAIL,
        ResultLevel.FAIL,
        ResultLevel.WARN,
    ]


def test_non_linux_platform_fails() -> None:
    assert (
        platform_checks(system="Windows", machine="arm64", python_version=(3, 12), os_release={})[
            -1
        ].level
        is ResultLevel.FAIL
    )


def test_os_release_parser_does_not_execute_values(tmp_path: Path) -> None:
    path = tmp_path / "os-release"
    path.write_text('ID="debian"\nVERSION_ID=13\n# ignored\nBAD=$(whoami)\n', encoding="utf-8")

    assert read_os_release(path) == {"ID": "debian", "VERSION_ID": "13", "BAD": "$(whoami)"}


def test_service_and_bluetooth_checks() -> None:
    runner = FakeRunner(
        [CommandResult(0, "active"), CommandResult(0, "Controller one\n Powered: yes")]
    )

    results = service_checks(runner)  # type: ignore[arg-type]

    assert [result.level for result in results] == [ResultLevel.PASS, ResultLevel.PASS]
    assert runner.commands[1] == ("bluetoothctl", "--timeout", "2", "show")


def test_dependency_checks_report_fixed_missing_packages() -> None:
    runner = FakeRunner(
        [
            CommandResult(0, "install ok installed")
            if dependency.package != "bluez"
            else CommandResult(1)
            for dependency in DEPENDENCIES
        ]
    )

    results, missing = dependency_checks(runner)  # type: ignore[arg-type]

    assert [dependency.package for dependency in missing] == ["bluez"]
    assert (
        next(result for result in results if result.name.startswith("Package bluez ")).level
        is ResultLevel.WARN
    )
    assert all(command[:3] == ("dpkg-query", "-W", "-f=${Status}") for command in runner.commands)


def test_command_runner_bounds_execution_failures() -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise OSError("not installed")

    runner = CommandRunner(unavailable)  # type: ignore[arg-type]
    assert runner.run(("missing",)).returncode == 127


def test_missing_os_release_is_empty(tmp_path: Path) -> None:
    assert read_os_release(tmp_path / "missing") == {}


def test_service_failures_are_classified_without_raw_output() -> None:
    runner = FakeRunner([CommandResult(1, "private detail"), CommandResult(1, "private detail")])

    results = service_checks(runner)  # type: ignore[arg-type]

    assert [result.level for result in results] == [ResultLevel.FAIL, ResultLevel.WARN]
    assert all("private detail" not in result.detail for result in results)
