# Dependency and licence audit

Reviewed 8 September 2026. Original gateway code remains MIT. No external application
source was copied or adapted during this audit. Historical protocol sources and
exact reviewed revisions remain in [provenance](provenance.md).

## Evidence and reproducibility

`pitblu-core/scripts/dependency_inventory.py` follows the installed runtime, development and
build-tool requirements for the executing platform. It records versions, declared
licences, upstream version-page links and hashes of installed notice files without
including local absolute paths, credentials or application data. CI saves one
inventory per supported Python version alongside a pip-audit JSON report. These are
resolved-environment records, not a cross-platform lock file or a signed SBOM.

Local inspection used Windows/Python 3.14 as a development environment; supported
Linux/Python 3.11, 3.12 and 3.13 inventories are a separate CI gate. The Pi target
is Linux/aarch64. Distribution markers select Linux dbus-fast rather than Windows
WinRT packages. OS-installed BlueZ, systemd and Mosquitto are not bundled Python
dependencies and remain subject to the distribution's updates and notices.

During clean-Pi acceptance, the same script and pinned Hatchling 1.32.0 build
requirement produced a valid Linux/aarch64 Python 3.13.5 inventory of roughly 18 KB.
Sanitisation checks found no home or managed-state paths, authorisation values,
bearer tokens or password strings. The generated Pi file is not committed because
it is a platform-specific resolved snapshot, not maintained source, a lock file or
a signed SBOM. CI remains the normal source of per-Python inventory and audit
artefacts.

The local pip-audit 2.10.1 query returned no known advisories for installed packages.
The private project itself is not on PyPI and was explicitly reported as skipped;
its security review is source-based. Tooling and build dependencies are rechecked
in CI after installation. A clean scan does not establish absence of vulnerabilities.

## Reviewed packages and obligations

Exact CI versions may differ for transitive dependencies; consult the corresponding
inventory artifact, not this local snapshot, when reproducing that environment.

| Group | Locally inspected versions / licence |
| --- | --- |
| Direct runtime | aiomqtt 2.5.1 BSD-3-Clause; bleak 3.0.2 MIT; fastapi 0.141.1 MIT; PyYAML 6.0.3 MIT; uvicorn 0.52.4 BSD-3-Clause |
| Runtime transitives | annotated-doc 0.0.5 MIT; annotated-types 0.8.0 MIT; anyio 4.15.0 MIT; click 8.5.0 BSD-3-Clause; h11 0.16.0 MIT; idna 3.19 BSD-3-Clause; pydantic 2.13.5 MIT; pydantic-core 2.46.5 MIT; starlette 1.6.0 BSD-3-Clause; typing-inspection 0.4.4 MIT; typing-extensions 4.16.0 PSF-2.0 |
| MQTT transport | paho-mqtt 2.1.0 EPL-2.0 OR BSD-3-Clause; select BSD-3-Clause |
| Linux BLE | dbus-fast 5.0.22 MIT, version metadata independently checked on PyPI; actual Linux resolution recorded by CI |
| Windows only | winrt-runtime and eight winrt-Windows namespace packages 3.2.1 MIT; not part of the Pi installation |
| Development | httpx2/httpcore2 2.12.0 BSD-3-Clause; mypy 2.3.1 MIT; mypy-extensions 1.1.0 MIT; librt 0.15.0 MIT; ast-serialize 0.9.0 MIT; pytest 9.1.1 MIT; pytest-cov 7.1.0 MIT; ruff 0.16.6 MIT; types-PyYAML 6.0.12.20260815 Apache-2.0 |
| Additional tooling | coverage 7.16.0 Apache-2.0; iniconfig 2.3.0 MIT; pluggy 1.6.0 MIT; pygments 2.21.0 BSD-2-Clause; colorama 0.4.6 BSD-3-Clause; truststore 0.10.4 MIT; packaging 26.3 Apache-2.0 OR BSD-2-Clause; pathspec 1.1.1 MPL-2.0 |
| Isolated build root | hatchling 1.32.0 MIT; its resolved transitive notices are included in the CI build-tool inventory |

The local build environment resolved tomlkit 0.15.1 (MIT) and trove-classifiers
2026.6.1.19 (Apache-2.0) in addition to packaging/pathspec/pluggy. Check the inventory's
classifiers/notice files when an SPDX expression is absent. GitHub Actions are
pinned to exact reviewed tag-target commits; Dependabot can propose updates.

MIT/BSD/PSF/Apache dependencies retain their original copyright, licence and notice
files in installed distributions. Do not strip these when redistributing an installed
environment. The project's MIT licence applies to its own code, not a relicensing
of dependencies. Select the stated BSD option for Paho; packaging offers a choice
of Apache-2.0 or BSD-2-Clause. Pathspec is an unmodified build/development tool under
MPL-2.0, not incorporated gateway source. If distributing that tool or modifying its
covered files, preserve its licence/source-availability obligations; source-only
gateway archives do not contain its code. The same care applies to any future
bundled image or virtual environment, which needs its own distribution review.

The broader local environment also contains certifi 2026.7.22 (MPL-2.0), httpcore
1.0.9 and pip, but the dependency-closure inventory does not falsely label unrelated
installed tools as required gateway dependencies.

Primary evidence includes the installed distribution metadata/notice texts and the
maintainer-published version pages for [Bleak](https://pypi.org/project/bleak/3.0.2/),
[FastAPI](https://pypi.org/project/fastapi/0.141.1/),
[Paho](https://pypi.org/project/paho-mqtt/2.1.0/),
[dbus-fast](https://pypi.org/project/dbus-fast/5.0.22/),
[typing-extensions](https://pypi.org/project/typing-extensions/4.16.0/) and
[Hatchling](https://pypi.org/project/hatchling/1.32.0/).

## Linux CI findings

Run 34214942968 passed software tests on Python 3.11/3.12/3.13 and produced all
three dependency inventories. Linux resolved anyio 4.15.1 and ast-serialize 0.10.0
(both MIT), plus dbus-fast 5.0.22 (MIT); other shared project versions matched the
local inventory. The Python 3.12/3.13 scans had no known advisories. Python 3.11's
preinstalled setuptools 79.0.1 triggered
[GHSA-h35f-9h28-mq5c](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c),
an exclusion issue when building source archives on Unicode-normalising filesystems.
It is not a declared gateway runtime dependency. CI now explicitly installs
setuptools 83.0.0, the scanner's reported fixed version, before building/testing,
and reruns the scan rather than ignoring the finding. Final rerun evidence follows
in the milestone plan. The gateway itself uses Hatchling, not setuptools, to build.

## Publication boundary

Source releases contain the original project and its notices, not copied external
source or bundled site-packages. No known reviewed dependency requires changing the
original project's MIT licence under this distribution model. Keep the repository
private unless the owner explicitly chooses otherwise. The actual target Linux
resolution and clean wheel installation were reviewed for v0.9.0. Future releases
must repeat that review for their resolved dependencies and build artefacts.
