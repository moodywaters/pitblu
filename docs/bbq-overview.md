# Pitblu, in plain English

## What is it?

Think of `pitblu-core` as a helper sitting beside your barbecue. It runs on a
Raspberry Pi, connects to your Weber iGrill over Bluetooth, and passes the probe
temperatures and battery level to other software.

Your iGrill still measures the temperature. The Pi is the messenger, not another
thermometer and not a controller for your barbecue.

## What can it do today?

- Read temperatures from the supported Weber iGrill V202, with up to four probe channels.
- Report whether a probe is plugged in and whether its reading is still current.
- Report the iGrill battery level.
- Remember the thermometer you have chosen and, when enabled, try to reconnect
  after a lost connection.
- Start automatically when a properly installed Pi starts.
- Share live readings with a separate application.

The current release is v0.9.0 beta. Clean-Pi acceptance passed; the complete
four-probe physical suite and 16-hour soak remain v1.0.0 gates. Check the
[acceptance record](physical-acceptance.md) before relying on the gateway for an
unattended cook.

## What will I see on my phone?

There is no friendly phone or web dashboard in this project yet. This is the
behind-the-scenes part that a separate web application will use.

A future application could show graphs, organise cooks, label probes as “brisket”
or “barbecue”, and provide alarms. Those features are not provided by
`pitblu-core` today. It does not keep your temperature history, send notifications,
control the heat, or tell you that food is safely cooked.

Until a separate application is available, a technical helper can check readings
on the Pi. The [quick-start guide](bbq-quick-start.md) includes an optional check.

## What do the technical words mean?

| Word | Plain-English meaning |
| --- | --- |
| Raspberry Pi | The small computer running the helper. |
| Bluetooth | The short-range wireless link from the iGrill to the Pi. |
| API | The way an application asks for readings or tells the helper what to do. |
| MQTT | A delivery service that passes live readings to interested applications. It is optional. |
| SSE | A live feed an application can listen to for readings and changes. |
| Administrator token | A private access key. Keep it like a password. |
| Fresh reading | A recently received measurement, not an old value left on screen. |
| Simulated reading | Test data made by software, not your actual thermometer. |

You do not need to understand MQTT or SSE to use a finished web application. They
are choices for the person building or setting up that application.

## What do I need?

A supported iGrill and suitable probes, a Raspberry Pi with reliable power,
Bluetooth range between the two, and the software installed and set up. The
tested setup uses a Raspberry Pi 4 with 64-bit Raspberry Pi OS Trixie.
Someone comfortable setting up a Pi is currently needed for first-time installation.

Keep the Pi protected from heat and weather without putting it somewhere that
blocks the Bluetooth signal. Follow the thermometer and probe manufacturers'
instructions for placement and use.

The helper currently connects to one thermometer at a time. Another app, such as
the Weber phone app, can compete for that Bluetooth connection. Close it when
using the Pi connection.

## What should I trust during a cook?

A number on a screen is useful only if it is current. If a connection drops, treat
the last number as an old reading, not proof that the temperature has stayed the
same. Check the thermometer directly when in doubt.

Keep your usual checks and an independent way to measure temperature. This is
development-stage monitoring software, not a replacement for food-safety checks
or an unattended-cooking safety system. Do not rely on an alarm from this project:
it does not provide one.

## Where next?

- [Quick start for a cook](bbq-quick-start.md): everyday preparation and a simple reading check.
- [Installation guide](installation.md): for the person setting up the Pi.
- [Frontend integration guide](frontend-integration.md): for an AI or developer building the separate web application.
