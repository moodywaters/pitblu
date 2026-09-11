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

    bluetooth = command.run(("bluetoothctl", "--timeout", "2", "show"), timeout=5)
    if bluetooth.returncode != 0:
        checks.append(CheckResult(ResultLevel.WARN, "Bluetooth", "controller status unavailable"))
    elif any(line.strip() == "Powered: yes" for line in bluetooth.stdout.splitlines()):
        checks.append(CheckResult(ResultLevel.PASS, "Bluetooth", "controller powered"))
    else:
        checks.append(CheckResult(ResultLevel.FAIL, "Bluetooth", "controller is not powered"))
    return checks


def command_available(name: str) -> bool:
    return shutil.which(name) is not None
