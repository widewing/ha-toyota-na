# Changelog

## 2026-04-19

### Added

- GraphQL remote-command support for modern Toyota NA vehicles
- AppSync remote-command status subscription caching
- remote start `switch` entity
- tire pressure parsing from GraphQL `vehicleState.tires`
- diagnostics output for cached vehicle-status and remote-command WebSocket data

### Changed

- `24MM` remote commands now use GraphQL instead of the older REST command path
- lock-state aggregation now prefers the four door locks and keeps a last-known
  state for better device-page behavior
- GraphQL vehicle-status subscription now requests tire data
- status parsing now tolerates more Toyota status string variants

### Fixed

- stale Toyota auth callback handling for current login/MFA flow
- async reauth path missing `await`
- false `open` / `unlocked` states caused by treating unknown status values as
  negative states
- missing `24MM` entity support in the local patched flow

## Upstreaming note

For a conservative upstream PR, the safest scope is:

- keep legacy `17CY` behavior unchanged
- gate GraphQL remote-command execution to `24MM`
- leave older generations on the current path until they are separately tested
