# Guided terminal tools

The v1.0 terminal workflow is **install → configure → verify**. It is designed for a person using
the Raspberry Pi console or an interactive SSH session. Neither tool needs to run as root; each
privileged action is shown and delegated to `sudo` as a fixed command.

These tools are part of the v1.0 workstream and have automated coverage. The outstanding physical
Pi/iGrill and soak gates remain listed in [physical acceptance](physical-acceptance.md).

## Install or upgrade

Clone the reviewed GitHub revision, enter the component directory and start the guided installer:

```bash
git clone git@github.com:moodywaters/pitblu.git
cd pitblu/pitblu-core
./pitblu-core-install
```

The installer identifies an existing managed deployment and offers the appropriate action. Its
subcommands are useful when the required action is already known:

```text
pitblu-core-install check     check host support and packages
pitblu-core-install install   install a fresh managed service
pitblu-core-install upgrade   upgrade an existing managed service
```

Run it as your normal user. It reports Raspberry Pi OS/Debian 13 on aarch64 as supported, warns
about other plausible Debian-like systems and stops on an unsupported OS, Python or architecture.
Package results identify runtime/install, deployment, optional and acceptance/test-only groups.
Mosquitto is not required. If required packages are missing, installation is offered with the safe
default `No [y/N]`, then checked again before deployment continues.

Before a fresh install, the tool explains that `sudo` will create the dedicated account, protected
directories, versioned virtual environment and hardened systemd unit. The existing
`deploy/manage.sh` remains the single low-level implementation of those changes. Its administrator
token appears once, directly on the TTY. Save it immediately in a password manager: the wrapper
does not capture, repeat or log it, and the service stores only its hash.

After deployment, the tool can enable/start the service, checks the installed version, service,
local health endpoint and Bluetooth controller, and offers to open configuration. It is safe to
rerun: an existing install is never overwritten as a fresh install. If interrupted, inspect the
last result and rerun from the same reviewed checkout. Versioned releases and protected state make
the documented rollback path available if an upgrade failed after backup.

## Configure and verify

Run the interactive menu locally on the Pi:

```bash
pitblu-core-config
```

Or select a focused workflow:

```text
pitblu-core-config check      canonical support and diagnostics report
pitblu-core-config show       show effective settings and secret status safely
pitblu-core-config igrill     scan, register or manage a thermometer
pitblu-core-config mqtt       configure optional MQTT publishing
pitblu-core-config api        configure API bind, port and browser origins
pitblu-core-config restart    confirm, restart and verify local health
```

If the API port was changed, put the global option before the subcommand:

```bash
pitblu-core-config --port 8090 check
```

The administrator token is accepted only through a hidden TTY prompt. It is never a command-line
option, environment variable or printed result. The tool always connects to `127.0.0.1`; it is not
a remote administration client. Configuration is read from the REST API, validated using the
existing complete model and saved with its ETag. A concurrent update fails instead of being
silently overwritten. The MQTT password uses the write-only secret endpoint and is never read back.

### Add an iGrill

Choose **Set up iGrill** or run `pitblu-core-config igrill`. Keep the thermometer awake and nearby,
select it by safe name/model/signal information, optionally name it, then connect. The tool passes
the API's opaque temporary discovery ID directly back to the registration endpoint; Bluetooth
addresses are never displayed. If the result expires, choose the offered rescan. Existing devices
can be connected, disconnected, reconnected, renamed or have automatic reconnection changed.

The final view reports desired/observed state, fresh probe count and battery freshness. Only one
thermometer can own the adapter at a time, as in the service itself. The CLI never creates a second
`bluetoothctl` connection path.

### Configure MQTT

`pitblu-core-config mqtt` controls enablement, broker host/port, TLS, username and base topic. QoS
remains the supported fixed value 1. A password is entered without echo and sent only to the
write-only endpoint. A broker—local, remote or hosted—is provisioned separately. If restart is
accepted, the tool verifies local API health and reports the resulting MQTT state. Broker delivery
still requires the physical/release acceptance procedure.

### Configure API access

The default remains `127.0.0.1:8080`. Selecting network listening displays a plain-language warning
and requires a second explicit confirmation. Token authentication remains enabled. Plain HTTP on
`0.0.0.0` is suitable only for a trusted local network behind appropriate controls; never expose it
directly to the internet. Browser origins are explicit and an empty list disables CORS.

All saved application settings require restart. Declining the restart leaves the new values safely
stored for the next service start. Restart uses only `sudo systemctl restart pitblu-core.service`
and verifies the health endpoint afterward.

## The canonical support report

Run this first whenever installation or operation is in doubt:

```bash
pitblu-core-config check
```

It reports platform/Python support, service and Bluetooth state, API health and authenticated
readiness, installed runtime version, clock synchronisation, MQTT state, registered devices,
desired versus observed connections, fresh probe counts and battery freshness. PASS, WARN and FAIL
are always written as words. Colour is added only on a TTY and is disabled whenever `NO_COLOR` is
set. The report excludes credentials, Bluetooth addresses, logs, databases and raw configuration.

Common results and next steps are in [troubleshooting](troubleshooting.md). A WARN can describe an
optional package, disabled MQTT, no registered device or temporarily unavailable reading; read its
text before deciding whether action is required. A FAIL means the supported workflow could not
verify a required layer.

## Expert and recovery path

The guided installer is the normal path. `deploy/manage.sh` remains available for controlled
backup, upgrade, rollback, uninstall and recovery as documented in
[backup, upgrade and rollback](upgrade-and-rollback.md). Uninstall removes the configuration
launcher because there is no service to configure, while preserving `pitblu-core-install` and all
managed data. The preserved launcher can check the host and direct a recovery operator back to a
fresh GitHub checkout; it is not a substitute for reviewed release source.
