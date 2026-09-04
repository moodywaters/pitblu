# Development

Use an isolated Python 3.11, 3.12 or 3.13 virtual environment. The required formatting, linting,
typing and test commands are in `README.md` and run in CI on all three Python versions.

Hardware tests are manual and gated. Ordinary CI does not require Bluetooth hardware. New protocol
facts need sanitised evidence and an update to `docs/provenance.md`.

