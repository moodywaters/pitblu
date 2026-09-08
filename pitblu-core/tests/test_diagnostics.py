import asyncio

from pitblu_core.diagnostics import HostDiagnostics


def test_host_diagnostics_are_cached_safe_and_explicit_about_unknown() -> None:
    async def exercise() -> None:
        calls: list[tuple[str, ...]] = []
        ticks = [0.0]

        async def reader(*args: str) -> str:
            calls.append(args)
            return (
                "Controller private-data\n\tPowered: yes" if args[0] == "bluetoothctl" else "no\n"
            )

        host = HostDiagnostics(reader=reader, clock=lambda: ticks[0], platform="linux")
        assert await host.snapshot() == {"bluetoothPowered": True, "clockSynchronized": False}
        assert "private-data" not in str(await host.snapshot())
        assert len(calls) == 2
        ticks[0] = 16
        await host.snapshot()
        assert len(calls) == 4

        async def unavailable(*args: str) -> str:
            raise OSError("private diagnostic details")

        assert await HostDiagnostics(reader=unavailable, platform="linux").snapshot() == {
            "bluetoothPowered": None,
            "clockSynchronized": None,
        }
        assert await HostDiagnostics(reader=unavailable, platform="win32").snapshot() == {
            "bluetoothPowered": None,
            "clockSynchronized": None,
        }

    asyncio.run(exercise())
