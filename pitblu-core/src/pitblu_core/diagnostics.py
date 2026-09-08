"""Read-only host health with bounded commands and no private command output."""

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from time import monotonic


async def _read(*arguments: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, "LC_ALL": "C"},
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
        if process.returncode != 0:
            raise OSError("host diagnostic unavailable")
        return output.decode(errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class HostDiagnostics:
    def __init__(
        self,
        *,
        reader: Callable[..., Awaitable[str]] = _read,
        clock: Callable[[], float] = monotonic,
        platform: str = sys.platform,
    ) -> None:
        self._reader = reader
        self._clock = clock
        self._platform = platform
        self._expires = float("-inf")
        self._lock = asyncio.Lock()
        self._result: dict[str, bool | None] = {"bluetoothPowered": None, "clockSynchronized": None}

    async def snapshot(self) -> dict[str, bool | None]:
        async with self._lock:
            if self._clock() < self._expires:
                return self._result.copy()
            powered = synchronized = None
            if self._platform == "linux":
                try:
                    output = await self._reader("bluetoothctl", "--timeout", "2", "show")
                    fields = {line.strip() for line in output.splitlines()}
                    if "Powered: yes" in fields:
                        powered = True
                    elif "Powered: no" in fields:
                        powered = False
                except (OSError, TimeoutError):
                    pass
                try:
                    output = await self._reader(
                        "timedatectl", "show", "--property=NTPSynchronized", "--value"
                    )
                    if output.strip() in {"yes", "no"}:
                        synchronized = output.strip() == "yes"
                except (OSError, TimeoutError):
                    pass
            self._result = {"bluetoothPowered": powered, "clockSynchronized": synchronized}
            self._expires = self._clock() + 15
            return self._result.copy()
