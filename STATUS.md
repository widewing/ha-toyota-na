# HA Toyota NA Status

Last updated: 2026-04-19

## Current state

Tested vehicle:

- `2026 RAV4 LE`
- generation: `24MM`

Verified working in Home Assistant:

- auth and reauth flow
- vehicle discovery
- door/lock/window/hood/trunk status
- lock / unlock commands
- remote start / stop
- hazards
- tire pressure

## Main implementation result

For `24MM`, remote commands now use the app-style GraphQL path:

- `SendRemoteCommand`
- `ReceiveRemoteCommandStatus`

The older REST command endpoint is not the correct execution path for this
vehicle generation.

## Notable fixes in this repo

- auth callback handling updated for current Toyota prompts and MFA
- missing `await` on reauth path fixed
- `24MM` generation handling added
- entity creation improved so entities register earlier
- GraphQL remote-command mutation added
- remote-command AppSync subscription added
- door/lock parser cleaned up to avoid false `open` / `unlocked`
- main lock entity behavior improved for device-page usability
- remote start switch entity added
- GraphQL tire-pressure parsing added from `vehicleState.tires`
- diagnostics extended with cached WebSocket payloads

## Known behavior notes

- Home Assistant polls every 10 minutes.
- A heavier Toyota-side refresh request is rate-limited by the integration to
  every 2 hours unless a command or manual refresh is triggered.
- Some telemetry can remain `unknown` if Toyota does not send it for the
  current vehicle/session.

## Files most affected

- `custom_components/toyota_na/patch_client.py`
- `custom_components/toyota_na/websocket_handler.py`
- `custom_components/toyota_na/patch_seventeen_cy_plus.py`
- `custom_components/toyota_na/lock.py`
- `custom_components/toyota_na/switch.py`
- `custom_components/toyota_na/diagnostics.py`
