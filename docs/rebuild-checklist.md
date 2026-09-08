# Fresh-OS rebuild checklist

The repository contains the gateway source, pinned direct Python requirements,
native installer, systemd unit, startup configuration template, tests, protocol
fixtures, API/MQTT documentation and licence notices. The web component is a
placeholder, not a deployable frontend.

## Before erasing storage

Keep a verified full-card image and protected application and broker backups on
another device. GitHub is source control, not a backup of a running deployment.
It intentionally does not contain administrator tokens, MQTT passwords/password
files, broker ACLs, device registrations, private addresses, SSH configuration or
the administrative SQLite database. Store credentials privately.

The repository is currently private. Confirm authenticated GitHub access from
another machine and download a source archive of the exact candidate revision
before erasing the Pi. Record that revision with the test results. Do not assume
a candidate has a published release asset. A repository source archive includes
both components and shared docs; install from its pitblu-core directory.

## Rebuild dependencies

Install fresh supported Raspberry Pi OS, configure secure SSH and network access,
and apply OS updates. Follow [native installation](installation.md) for required
OS packages and the gateway installer. Package-index/network access is required;
Python wheels and OS packages are not vendored in the repository.

For API-only operation, leave MQTT disabled. To test MQTT, independently install
or provision a broker with password authentication and no anonymous access.
Give the gateway a dedicated pitblu-core publisher identity with access to
pitblu/#. Configure broker location, TLS where appropriate, username and base topic
through the API, and the password through the write-only secret endpoint. The
gateway installer deliberately does not install or configure Mosquitto.

## Clean installation versus restoration

For clean-Pi acceptance, bootstrap a new token and register the thermometer through
REST. Do not restore old application state/configuration as part of that test.
Configure the broker independently and verify physical MQTT delivery. Keep recovery
backups untouched. Complete the [clean-Pi procedure](clean-pi-acceptance.md) and
record failures as well as successes before declaring the gate passed.

A full image restoration is a recovery option, not evidence of a clean installation.
Do not operate two gateway instances against the same thermometer.
