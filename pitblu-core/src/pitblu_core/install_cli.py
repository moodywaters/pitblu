"""Guided, unprivileged installer for native pitblu-core deployments."""

from __future__ import annotations

import argparse
import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from pitblu_core.api_client import ApiClient, ApiError
from pitblu_core.system_checks import (
    CommandRunner,
    Dependency,
    dependency_checks,
    platform_checks,
    service_checks,
)
from pitblu_core.terminal import CheckResult, ResultLevel, Terminal

_EFFECTIVE_UID: Callable[[], int] | None = getattr(os, "geteuid", None)


class ForegroundExecutor(Protocol):
    def __call__(self, arguments: Sequence[str]) -> int: ...


def execute_foreground(arguments: Sequence[str]) -> int:
    """Run a fixed argument array with inherited terminal streams."""

    try:
        return subprocess.run(list(arguments), check=False).returncode
    except OSError:
        return 127


class InstallApplication:
    """Guide checks and delegate system changes to the reviewed deployment script."""

    def __init__(
        self,
        *,
        source_root: Path | None,
        terminal: Terminal | None = None,
        command_runner: CommandRunner | None = None,
        foreground: ForegroundExecutor = execute_foreground,
        deployment_root: Path = Path("/opt/pitblu-core"),
        unit_path: Path = Path("/etc/systemd/system/pitblu-core.service"),
        effective_uid: Callable[[], int] | None = _EFFECTIVE_UID,
    ) -> None:
        self.source_root = source_root
        self.terminal = terminal or Terminal()
        self._commands = command_runner or CommandRunner()
        self._foreground = foreground
        self._deployment_root = deployment_root
        self._unit_path = unit_path
        self._effective_uid = effective_uid

    @property
    def installed(self) -> bool:
        return (self._deployment_root / "current").exists() or self._unit_path.exists()

    def check(self) -> int:
        self.terminal.heading("pitblu-core installation check")
        checks = platform_checks()
        dependencies, _missing = dependency_checks(self._commands)
        level = self.terminal.results([*checks, *dependencies])
        return 1 if level is ResultLevel.FAIL else 0

    def guided(self) -> int:
        if not self.terminal.interactive:
            self.terminal.write("Use pitblu-core-install check, install, or upgrade in a terminal.")
            return 2
        self.terminal.heading("pitblu-core guided installer")
        action = "upgrade" if self.installed else "install"
        self.terminal.write(
            "An existing deployment was found; upgrade is available."
            if self.installed
            else "No existing deployment was found; a fresh install is available."
        )
        if not self.terminal.confirm(f"Continue with {action}?"):
            return 0
        return self.deploy(action)

    def deploy(self, action: str) -> int:
        if action not in {"install", "upgrade"}:
            raise ValueError("unsupported deployment action")
        if not self.terminal.interactive:
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Installer", "installation requires a terminal")
            )
            return 1
        if self._effective_uid is not None and self._effective_uid() == 0:
            self.terminal.result(
                CheckResult(
                    ResultLevel.FAIL,
                    "Installer",
                    "run as your normal user; the installer requests sudo only when needed",
                )
            )
            return 1
        if (action == "install" and self.installed) or (action == "upgrade" and not self.installed):
            expected = "upgrade" if self.installed else "install"
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Installer", f"use the {expected} command instead")
            )
            return 1
        script = self._deployment_script()
        checks = platform_checks()
        dependencies, missing = dependency_checks(self._commands)
        level = self.terminal.results([*checks, *dependencies])
        if level is ResultLevel.FAIL:
            return 1
        if missing and not self._install_dependencies(missing):
            self.terminal.write("Dependencies were not installed. No deployment changes were made.")
            return 1
        if action == "install":
            self.terminal.heading("Administrator token")
            self.terminal.write(
                "The administrator token will be shown once by the installer. Save it now in a "
                "secure password manager; it cannot be displayed again."
            )
        if self._foreground(("sudo", "bash", str(script), action)) != 0:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "Deployment", f"{action} failed"))
            return 1
        if (
            action == "install"
            and self.terminal.confirm("Enable and start pitblu-core now?", default=True)
            and self._foreground(("sudo", "systemctl", "enable", "--now", "pitblu-core.service"))
            != 0
        ):
            self.terminal.result(CheckResult(ResultLevel.FAIL, "Service", "could not start"))
            return 1
        result = self._post_install_check()
        if result == 0 and self.terminal.confirm("Open guided configuration now?", default=True):
            result = self._foreground(("/usr/local/bin/pitblu-core-config",))
        return result

    def _deployment_script(self) -> Path:
        if self.source_root is None:
            raise ApiError(
                "Install or upgrade from a fresh GitHub checkout using its "
                "pitblu-core-install launcher"
            )
        root = self.source_root.resolve()
        script = (root / "deploy" / "manage.sh").resolve()
        if script.parent != root / "deploy" or not script.is_file():
            raise ApiError("The source checkout does not contain deploy/manage.sh")
        return script

    def _install_dependencies(self, missing: Sequence[Dependency]) -> bool:
        packages = tuple(dependency.package for dependency in missing)
        self.terminal.write(f"Missing Debian packages: {', '.join(packages)}")
        if not self.terminal.confirm("Install these dependencies with apt?"):
            return False
        if self._foreground(("sudo", "apt-get", "update")) != 0:
            self.terminal.result(CheckResult(ResultLevel.FAIL, "Dependencies", "apt update failed"))
            return False
        command = ("sudo", "apt-get", "install", "--yes", *packages)
        if self._foreground(command) != 0:
            self.terminal.result(
                CheckResult(ResultLevel.FAIL, "Dependencies", "apt install failed")
            )
            return False
        self.terminal.result(CheckResult(ResultLevel.PASS, "Dependencies", "installed"))
        return True

    def _post_install_check(self) -> int:
        self.terminal.heading("Post-install checks")
        checks = service_checks(self._commands)
        try:
            health = ApiClient().get("/health", authenticated=False)
            healthy = isinstance(health.data, dict) and health.data.get("status") == "ok"
            checks.append(
                CheckResult(
                    ResultLevel.PASS if healthy else ResultLevel.FAIL,
                    "Local API",
                    "healthy" if healthy else "unexpected response",
                )
            )
        except ApiError as exc:
            checks.append(CheckResult(ResultLevel.FAIL, "Local API", str(exc)))
        return 1 if self.terminal.results(checks) is ResultLevel.FAIL else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pitblu-core-install")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("check", help="check host support and required dependencies")
    subcommands.add_parser("install", help="perform a fresh native installation")
    subcommands.add_parser("upgrade", help="upgrade an existing native installation")
    return parser


def main(arguments: Sequence[str] | None = None, *, source_root: Path | None = None) -> int:
    args = build_parser().parse_args(arguments)
    application = InstallApplication(source_root=source_root)
    try:
        if args.command is None:
            return application.guided()
        if args.command == "check":
            return application.check()
        return application.deploy(args.command)
    except ApiError as exc:
        application.terminal.result(CheckResult(ResultLevel.FAIL, "Installer", str(exc)))
        return 1
