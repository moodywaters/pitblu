# Development

Use an isolated Python 3.11, 3.12 or 3.13 virtual environment. The required formatting, linting,
typing and test commands are in `README.md` and run in CI on all three Python versions.

Hardware tests are manual and gated. Ordinary CI does not require Bluetooth hardware. New protocol
facts need sanitised evidence and an update to `docs/provenance.md`.

The deterministic simulator uses the production adapter models and is the default test double for
device-level behaviour. Tests may configure one to four probes, rising, falling or stable patterns,
probe presence, battery percentage, stale snapshots and connection availability without real-time
sleeps. Connection backoff accepts an injected random source so boundary values are deterministic.

The fixture under `tests/fixtures/v202/` contains only protocol payloads and manual display values
from the accepted v0.1.0 run. It must never contain a Bluetooth address or private network data.
The manual `pitboss-v202-check` command exercises the production adapter rather than the simulator.
