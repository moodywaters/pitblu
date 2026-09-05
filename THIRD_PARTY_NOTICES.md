# Third-party notices

No third-party source code has been copied or substantially adapted into this repository.

Runtime dependencies are aiomqtt 2.5.1 under the BSD 3-Clause Licence, Bleak 3.0.2 under the MIT
Licence, FastAPI 0.141.1 under the MIT Licence, PyYAML 6.0.3 under the MIT Licence, and Uvicorn
0.52.4 under the BSD 3-Clause Licence. aiomqtt carries copyright 2020 SBT Instruments. Its Paho
MQTT Python 2.1.0 transport dependency is available under `EPL-2.0 OR BSD-3-Clause`; this project
uses the BSD 3-Clause option. Copyright notices and complete licence texts remain in their
installed distributions. Platform-specific and framework transitive dependencies are installed
with those packages and retain their own notices.

Development dependencies include Hatchling, HTTPX2, mypy, pytest, pytest-cov and Ruff. HTTPX2 is
under the BSD 3-Clause Licence; the other tools are under their licences recorded in
`docs/provenance.md`. Development tooling is not distributed with the application.

The Weber iGrill UUIDs, sentinel and authentication exchange were independently implemented from
protocol facts corroborated across the research sources recorded in `docs/provenance.md`. Their
source licences and exact reviewed revisions are recorded there.
