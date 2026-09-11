# Quick start for a cook

This guide is for v0.9.0. There is no phone-friendly dashboard
yet. Start with [the plain-English overview](bbq-overview.md) if you are new to the
project.

## First time only

Ask the person setting up your Pi to follow the [installation guide](installation.md).
They need to install the service, save its private administrator token, register
your iGrill, and enable automatic reconnection if you want it. Installation alone
does not select a nearby thermometer for you.

Before handing it over, ask them to demonstrate both a current probe reading that
matches the iGrill display and the battery level. Keep the token in a password
manager. Do not paste it into a chat or share a screenshot of it.

If your Pi is already installed and your thermometer registered, do not reinstall
anything for each cook.

## Before lighting the barbecue

1. Power the Pi and turn on the iGrill. Check the iGrill battery before starting
   a long cook.
2. Plug in the probes you intend to use. Check their readings on the iGrill itself.
3. Keep the Pi within dependable Bluetooth range, safely away from heat and weather.
4. Close the Weber phone app and other software that might connect to the same iGrill.
5. Give the Pi a minute or two to connect. If you previously chose Disconnect,
   your setup helper needs to connect it again; automatic recovery respects that choice.
6. Check that the software reports physical, current readings and that they agree
   with the thermometer. A solid Bluetooth light alone is not proof that readings
   are reaching the software.

Do not start an upgrade, rollback or recovery experiment during a cook. Those can
interrupt monitoring.

## Check readings now, without a web dashboard

Use the Raspberry Pi terminal or your SSH connection to it and run the supported check:

```bash
pitblu-core-config check
```

Enter your administrator token when asked; nothing appears as you type. That is normal. The check
does not change settings. It reports the service version and health, thermometer connection, fresh
probe readings, battery and optional MQTT state without showing tokens or Bluetooth addresses.

This assumes the standard local port. If it was changed, use
`pitblu-core-config --port PORT check`. Run it again for a new snapshot; the printed numbers do not
update by themselves. The complete terminal workflow is in [guided terminal tools](terminal-tools.md).

## What does the result mean?

| What you see | What to do |
| --- | --- |
| `polling` and current physical temperatures | Readings are arriving. Compare with the iGrill display. |
| `connecting`, `initialising` or `backoff` | It is connecting or waiting to try again. Allow time, then check power, range and competing apps. |
| `disconnected` | It is not currently connected. Ask your setup helper to check whether Disconnect was selected. |
| No current reading | Do not treat an earlier temperature as live. Check the thermometer directly. |
| Not plugged in | Expected for an unused socket. If you inserted a probe, check its connection. |
| TEST DATA | This is simulation, not your barbecue. Ask your setup helper to select physical mode. |
| Helper responding, but no probe readings | The Pi software is running, but that does not prove the Bluetooth connection is working. |

## During a cook

Keep the Pi powered and the thermometer in range. Continue checking the iGrill and
the food as you normally would. If readings stop, check the iGrill's power, probes
and battery, and close any competing phone app. Do not repeatedly disconnect,
restart or re-pair devices while the software is already trying to recover.

If it still does not recover after a few minutes, ask your setup helper to
investigate. Tell them when it stopped and what the iGrill display shows, but do
not send passwords, access tokens or unreviewed logs.

There are no built-in alerts, cooking targets or temperature-history graphs.
The minimum 16-hour physical reliability test is still a v1.0.0 release requirement,
not a completed guarantee for overnight cooks. Keep independent temperature checks.

## After the cook

Turn off the iGrill when finished. With automatic reconnection enabled, the helper
may keep looking for it; missing readings are then expected. A deliberate software
Disconnect stops those retries, but someone must select Connect again next time.

The Pi can stay running. If you want to switch it off, shut it down properly before
removing power. Remember that this project has not saved a graph or record of your
cook; that requires the separate application.
