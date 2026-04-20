# ha-toyota-na

Home Assistant custom integration for Toyota North America.

This local repo contains additional Toyota NA fixes validated against a
`2026 RAV4 LE` (`24MM`) and is ahead of the original upstream behavior in a few
important areas.

## Current tested status

Working on the tested `24MM` vehicle:

- login and MFA
- vehicle discovery
- door, lock, hood, trunk, and window status
- lock / unlock
- remote start / stop
- hazards
- tire pressure from the GraphQL vehicle-status feed

Still dependent on Toyota-provided data quality:

- some telemetry fields may remain `unknown` if Toyota does not return them
  consistently for the vehicle/account

## Important architecture note

For modern `24MM` vehicles, the app's working remote-command path is GraphQL,
not the older REST remote-command endpoint.

Working command path:

- GraphQL mutation `SendRemoteCommand`
- GraphQL subscription `ReceiveRemoteCommandStatus`

The older REST endpoint can still return `ONE-GLOBAL-RS-40009` and should not be
treated as the source of truth for `24MM` command execution.

The `24MM` app vehicle-status GraphQL payload also includes:

- `vehicleState.tires`

That is the source used here for tire pressure.

## Current features

Certain entities and services require a Toyota remote subscription.

Controls / services:

- lock / unlock doors
- remote start / stop engine
- hazards on / off
- refresh data

Vehicle status / sensors:

- door lock status
- window and moonroof status
- trunk status
- real-time location
- last parked location
- tire pressure
- fuel level
- odometer
- last update
- last tire pressure update
- speed
- EV plug / charging status where supported

## Installation

### HACS

1. Install HACS: [https://hacs.xyz/docs/setup/download](https://hacs.xyz/docs/setup/download)
2. Add this repo as a custom integration source if using this patched version.

### Manual installation

1. Copy `/custom_components/toyota_na/` into your Home Assistant
   `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from the UI.

## Configuration

Add the integration from Home Assistant and enter your Toyota username and
password. Toyota may require an emailed OTP / MFA code during setup or later
reauthentication.

## Files worth reading

- [STATUS.md](/mnt/c/Users/trevj/Projects/ha-toyota-na/STATUS.md)
- [CHANGELOG.md](/mnt/c/Users/trevj/Projects/ha-toyota-na/CHANGELOG.md)
- [UPSTREAM_PR_NOTES.md](/mnt/c/Users/trevj/Projects/ha-toyota-na/UPSTREAM_PR_NOTES.md)

## Credits

Thanks to the original `ha-toyota-na` project and prior Toyota integration
work that made the initial Home Assistant support possible.
