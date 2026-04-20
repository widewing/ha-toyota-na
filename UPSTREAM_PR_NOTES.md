# Upstream PR Notes

## Recommended scope

Keep the upstream change narrow and generation-aware.

Recommended first PR:

- add GraphQL remote-command support
- add remote-command AppSync subscription support
- use the GraphQL command path for `24MM`
- leave legacy `17CY` and older paths unchanged

## Why this scope

Observed on the tested `24MM` vehicle:

- GraphQL remote commands succeed
- REST remote commands fail with `ONE-GLOBAL-RS-40009`
- `confirmSubscriptionActive` may fail with `APPSYNC-429: Device limit exceeded`
  while remote commands still succeed

That means a broad “replace REST for everyone” PR would be riskier than needed.

## Evidence to cite

- Android app uses:
  - GraphQL mutation `SendRemoteCommand`
  - GraphQL subscription `ReceiveRemoteCommandStatus`
- Android app `GetVehicleStatus($vin)` includes:
  - `vehicleState.tires`
- Tested commands working through GraphQL:
  - `door-unlock`
  - `hazard-on`
  - remote start / stop through Home Assistant after patching

## Suggested PR breakdown

1. GraphQL remote-command path for `24MM`
2. GraphQL vehicle-status subscription expansion to include `tires`
3. parser hardening for unknown Toyota door/lock values
4. optional follow-up: remote start entity improvements

## Risks to call out

- older `21MM` / `17CYPLUS` vehicles were not fully regression-tested here
- Toyota may vary payload availability by trim, subscription, or account region
- telemetry completeness can still vary independently of command success
