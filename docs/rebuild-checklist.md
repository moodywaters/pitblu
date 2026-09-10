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

The repository is currently private. Confirm authenticated, least-privilege GitHub
access before erasing the Pi. For the normal rebuild path, clone the repository,
check out the exact reviewed release tag or full commit, and record its full revision
with the test results. Do not place GitHub credentials in commands or logs. An
archive produced by GitHub from the same revision is suitable for offline recovery,
but GitHub tags and releases are the authoritative release history.

## Rebuild dependencies

Install fresh supported Raspberry Pi OS, configure secure SSH and network access,
and apply OS updates. Follow [native installation](installation.md) for required
OS packages and the gateway installer. Package-index/network access is required;
Python wheels and OS packages are not vendored in the repository.

Git is required for the normal GitHub-source workflow. The remaining core and
administrative prerequisites are listed in the installation guide. For API-only
operation, leave MQTT disabled. To test MQTT, independently install or provision
a broker and client tools with password authentication and no anonymous access.
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
