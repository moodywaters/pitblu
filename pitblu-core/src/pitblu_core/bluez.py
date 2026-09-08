"""Bounded recovery of a single registered device's leftover BlueZ connection."""

import asyncio
import os
import re
import sys

from pitblu_core.adapters.base import AdapterError


async def _command(action: str, identity: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "bluetoothctl",
        "--timeout",
        "5",
        action,
        identity,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, "LC_ALL": "C"},
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=7)
        if process.returncode != 0:
            raise AdapterError("registered-device BlueZ command failed")
        return output
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def release_registered_connection(identity: str) -> bool:
    """Never unpair, scan by name, or reset an adapter; only release this identity."""
    if sys.platform != "linux" or not re.fullmatch(
        r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", identity
    ):
        return False
    try:
        info = await _command("info", identity)
        if not any(line.strip() == b"Connected: yes" for line in info.splitlines()):
            return False
        await _command("disconnect", identity)
        info = await _command("info", identity)
        if any(line.strip() == b"Connected: yes" for line in info.splitlines()):
            raise AdapterError("registered-device BlueZ connection could not be released")
        return True
    except (OSError, TimeoutError) as exc:
        raise AdapterError("registered-device BlueZ recovery unavailable") from exc
