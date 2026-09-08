import asyncio
import sys
from typing import Any

import pytest

from pitblu_core import bluez
from pitblu_core.adapters.base import AdapterError

IDENTITY = ":".join(["AA", "BB", "CC", "DD", "EE", "FF"])


@pytest.mark.parametrize("returncode", [0, 1])
def test_command_checks_exit_code(monkeypatch: pytest.MonkeyPatch, returncode: int) -> None:
    class Process:
        async def communicate(self) -> tuple[bytes, bytes]:
            return b"Connected: no", b""

    process = Process()
    process.returncode = returncode  # type: ignore[attr-defined]

    async def spawn(*args: Any, **kwargs: Any) -> Process:
        assert kwargs["env"]["LC_ALL"] == "C"
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    if returncode:
        with pytest.raises(AdapterError, match="command failed"):
            asyncio.run(bluez._command("info", IDENTITY))
    else:
        assert asyncio.run(bluez._command("info", IDENTITY)) == b"Connected: no"


def test_only_connected_exact_registered_identity_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    answers = [b"Connected: yes\n", b"", b"Connected: no\n"]

    async def command(action: str, identity: str) -> bytes:
        calls.append((action, identity))
        return answers.pop(0)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(bluez, "_command", command)
    assert asyncio.run(bluez.release_registered_connection(IDENTITY))
    assert calls == [(action, IDENTITY) for action in ("info", "disconnect", "info")]
    assert not asyncio.run(bluez.release_registered_connection("unregistered-name"))
    answers.append(b"Connected: no\n")
    assert not asyncio.run(bluez.release_registered_connection(IDENTITY))
    assert calls[-1] == ("info", IDENTITY)


def test_release_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    async def connected(action: str, identity: str) -> bytes:
        return b"Connected: yes\n"

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(bluez, "_command", connected)
    with pytest.raises(AdapterError, match="could not be released"):
        asyncio.run(bluez.release_registered_connection(IDENTITY))

    async def failed(action: str, identity: str) -> bytes:
        raise TimeoutError(IDENTITY)

    monkeypatch.setattr(bluez, "_command", failed)
    with pytest.raises(AdapterError, match="recovery unavailable") as error:
        asyncio.run(bluez.release_registered_connection(IDENTITY))
    assert IDENTITY not in str(error.value)


def test_subprocess_is_bounded_and_killed_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        returncode: int | None = None
        killed = False

        async def communicate(self) -> tuple[bytes, bytes]:
            raise asyncio.CancelledError

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            self.returncode = -9
            return -9

    process = Process()

    async def spawn(*args: Any, **kwargs: Any) -> Process:
        assert args == ("bluetoothctl", "--timeout", "5", "info", IDENTITY)
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bluez._command("info", IDENTITY))
    assert process.killed
