"""Host prerequisite and service checks for guided terminal workflows."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pitblu_core.terminal import CheckResult, ResultLevel


@dataclass(frozen=True, slots=True)
class Dependency:
    package: str
    purpose: str
    category: str
    required: bool = True


DEPENDENCIES = (
    Dependency("python3", "Python runtime", "runtime/install"),
    Dependency("python3-venv", "isolated Python environment", "runtime/install"),
    Dependency("bluez", "Bluetooth tools and service", "runtime/install"),
    Dependency("systemd", "service management", "deployment"),
    Dependency("util-linux", "deployment locking and service-account commands", "deployment"),
    Dependency("passwd", "dedicated service account", "deployment"),
    Dependency("git", "GitHub source checkout and updates", "runtime/install"),
    Dependency("ca-certificates", "verified HTTPS connections", "runtime/install"),
    Dependency("curl", "optional manual HTTP checks", "optional", required=False),
    Dependency(
        "mosquitto-clients",
        "optional MQTT acceptance checks",
        "acceptance/test-only",
        required=False,
    ),
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""


class CommandRunner:
    """Execute bounded argument arrays without a shell."""

    def __init__(
        self, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    ) -> None:
        self._run = run

    def run(self, arguments: Sequence[str], *, timeout: float = 15) -> CommandResult:
        try:
            completed = self._run(
                list(arguments),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return CommandResult(127)
        return CommandResult(completed.returncode, completed.stdout.strip())


def read_os_release(path: Path = Path("/etc/os-release")) -> dict[str, str]:
    """Read simple os-release values without evaluating the file as shell code."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
    return values


def platform_checks(
    *,
    system: str = platform.system(),
    machine: str = platform.machine(),
    python_version: tuple[int, int] = sys.version_info[:2],
    os_release: Mapping[str, str] | None = None,
) -> list[CheckResult]:
    """Apply the documented PASS/WARN/FAIL host support policy."""

    checks: list[CheckResult] = []
    architecture = machine.casefold()
    if architecture in {"aarch64", "arm64"}:
        checks.append(CheckResult(ResultLevel.PASS, "Architecture", machine))
    else:
        checks.append(
            CheckResult(
                ResultLevel.FAIL,
                "Architecture",
                f"{machine or 'unknown'} is unsupported; aarch64 is required",
            )
        )

    if (3, 11) <= python_version <= (3, 13):
        checks.append(CheckResult(ResultLevel.PASS, "Python", ".".join(map(str, python_version))))
    else:
        checks.append(
            CheckResult(
                ResultLevel.FAIL,
                "Python",
                f"{python_version[0]}.{python_version[1]} is unsupported; use 3.11 to 3.13",
            )
        )

    release = dict(os_release if os_release is not None else read_os_release())
    identifier = release.get("ID", "").casefold()
    like = release.get("ID_LIKE", "").casefold().split()
    version = release.get("VERSION_ID", "")
    pretty = release.get("PRETTY_NAME", identifier or system or "unknown")
    if system.casefold() != "linux":
        checks.append(CheckResult(ResultLevel.FAIL, "Operating system", f"{system} is unsupported"))
    elif identifier in {"debian", "raspbian"} and version == "13":
        checks.append(CheckResult(ResultLevel.PASS, "Operating system", pretty))
    elif identifier in {"debian", "raspbian", "ubuntu"} or "debian" in like:
        checks.append(
            CheckResult(
                ResultLevel.WARN,
                "Operating system",
                f"{pretty} is Debian-like but outside the fully supported target",
            )
        )
    else:
        checks.append(CheckResult(ResultLevel.FAIL, "Operating system", f"{pretty} is unsupported"))
    return checks


def service_checks(runner: CommandRunner | None = None) -> list[CheckResult]:
    """Check the installed service and local Bluetooth controller."""

    command = runner or CommandRunner()
    checks: list[CheckResult] = []
    service = command.run(("systemctl", "is-active", "pitblu-core.service"))
    if service.returncode == 0 and service.stdout == "active":
        checks.append(CheckResult(ResultLevel.PASS, "Service", "active"))
    else:
        checks.append(CheckResult(ResultLevel.FAIL, "Service", "not active"))

    checks.append(bluetooth_check(command))
    return checks


def bluetooth_check(runner: CommandRunner | None = None) -> CheckResult:
    """Check controller availability without exposing controller identifiers."""

    command = runner or CommandRunner()
    bluetooth = command.run(("bluetoothctl", "--timeout", "2", "show"), timeout=5)
    if bluetooth.returncode != 0:
        return CheckResult(ResultLevel.WARN, "Bluetooth", "controller status unavailable")
    if any(line.strip() == "Powered: yes" for line in bluetooth.stdout.splitlines()):
        return CheckResult(ResultLevel.PASS, "Bluetooth", "controller powered")
    return CheckResult(ResultLevel.FAIL, "Bluetooth", "controller is not powered")


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def dependency_checks(
    runner: CommandRunner | None = None,
) -> tuple[list[CheckResult], list[Dependency]]:
    """Report required Debian packages using fixed dpkg-query arguments."""

    command = runner or CommandRunner()
    checks: list[CheckResult] = []
    missing: list[Dependency] = []
    for dependency in DEPENDENCIES:
        result = command.run(("dpkg-query", "-W", "-f=${Status}", dependency.package), timeout=5)
        installed = result.returncode == 0 and result.stdout == "install ok installed"
        checks.append(
            CheckResult(
                ResultLevel.PASS if installed else ResultLevel.WARN,
                f"Package {dependency.package} [{dependency.category}]",
                dependency.purpose
                if installed
                else f"missing: {dependency.purpose}"
                + ("" if dependency.required else " (not required for normal operation)"),
            )
        )
        if not installed and dependency.required:
            missing.append(dependency)
    return checks, missing
