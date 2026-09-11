"""Small, testable terminal presentation helpers for the guided tools."""

from __future__ import annotations

import getpass
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, TextIO

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


class ResultLevel(StrEnum):
    """A machine-comparable check outcome with a readable terminal label."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One diagnostic or prerequisite check."""

    level: ResultLevel
    name: str
    detail: str


def safe_text(value: object) -> str:
    """Make external text safe to print without changing its useful content."""

    return _CONTROL_CHARACTERS.sub("?", str(value)).replace("\r", "?").replace("\n", " ")


class Terminal:
    """Terminal I/O kept behind an injectable boundary for safe prompting and tests."""

    _COLOURS: ClassVar[dict[ResultLevel, str]] = {
        ResultLevel.PASS: "\033[32m",
        ResultLevel.WARN: "\033[33m",
        ResultLevel.FAIL: "\033[31m",
    }

    def __init__(
        self,
        *,
        input_stream: TextIO = sys.stdin,
        output_stream: TextIO = sys.stdout,
        environ: Mapping[str, str] = os.environ,
        input_fn: Callable[[str], str] = input,
        secret_fn: Callable[[str], str] = getpass.getpass,
    ) -> None:
        self.input_stream = input_stream
        self.output_stream = output_stream
        self._input = input_fn
        self._secret = secret_fn
        self.colour = output_stream.isatty() and "NO_COLOR" not in environ

    @property
    def interactive(self) -> bool:
        """Return whether both ends of the conversation are terminals."""

        return self.input_stream.isatty() and self.output_stream.isatty()

    def write(self, message: object = "") -> None:
        print(safe_text(message), file=self.output_stream)

    def heading(self, title: object) -> None:
        self.write(f"\n{safe_text(title)}")

    def result(self, check: CheckResult) -> None:
        label = check.level.value
        if self.colour:
            label = f"{self._COLOURS[check.level]}{label}\033[0m"
        print(
            f"{label}  {safe_text(check.name)}: {safe_text(check.detail)}",
            file=self.output_stream,
        )

    def results(self, checks: Sequence[CheckResult]) -> ResultLevel:
        for check in checks:
            self.result(check)
        levels = {check.level for check in checks}
        if ResultLevel.FAIL in levels:
            return ResultLevel.FAIL
        if ResultLevel.WARN in levels:
            return ResultLevel.WARN
        return ResultLevel.PASS

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        suffix = " [Y/n] " if default else " [y/N] "
        while True:
            answer = self._input(f"{safe_text(prompt)}{suffix}").strip().casefold()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            self.write("Please answer y or n.")

    def ask(self, prompt: str, *, default: str | None = None) -> str:
        suffix = f" [{safe_text(default)}] " if default is not None else " "
        answer = self._input(f"{safe_text(prompt)}{suffix}").strip()
        return answer or (default if default is not None else "")

    def secret(self, prompt: str) -> str:
        """Read a value without echoing it; callers must not retain it unnecessarily."""

        return self._secret(f"{safe_text(prompt)}: ")
