# Development

Use an isolated Python 3.11, 3.12 or 3.13 virtual environment. CI runs on all three
versions. The current released baseline is v0.6.0; the active audit plan is v0.9.0.

## Setup and checks

From the repository root on Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy src tests
.venv/bin/python -m pytest
bash -n deploy/manage.sh
```

On Windows, create the environment with `python -m venv .venv` and use
`.venv\Scripts\python.exe` for the Python commands. Shell syntax checking requires
Bash; native installation and Bluetooth acceptance run on the Pi, not Windows.
Do not run a diagnostic adapter alongside the installed service on the same device.

## Documentation checks

Follow the [documentation policy](README.md). The frontend inventory test checks
route, setting and event coverage; the documentation-link test checks local links.
Review semantics and examples as well: link coverage alone does not prove accuracy.

Hardware tests are manual and gated. Ordinary CI does not require Bluetooth hardware. New protocol
facts need sanitised evidence and an update to `docs/provenance.md`.

The deterministic simulator uses the production adapter models and is the default test double for
device-level behaviour. Tests may configure one to four probes, rising, falling or stable patterns,
probe presence, battery percentage, stale snapshots and connection availability without real-time
sleeps. Connection backoff accepts an injected random source so boundary values are deterministic.

The fixture under `tests/fixtures/v202/` contains only protocol payloads and manual display values
from the accepted v0.1.0 run. It must never contain a Bluetooth address or private network data.
The manual `pitboss-v202-check` command exercises the production adapter rather than the simulator.
