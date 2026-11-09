# Changelog

## 0.1.0 - unreleased
- Native apps: `ConnectionsApi.startUrl(..., native: true)` adds `mode=native`; `ConnectionsApi.redeem(provider, code)`;
  `ConnectionReturn.code` (read by `parse`, dropped by `cleaned`).
- `ConnectionStatus` (fromJson/toJson), `ConnectionPhase` (disconnected, connected, needsReconnect; named so to
  avoid Flutter's `ConnectionState`).
- `ConnectionsApi` (`list`, `startUrl`, `disconnect`), `DemoConnectionsApi` (`simulateExpiry`).
- `ConnectionReturn.parse` / `cleaned` for the address the browser returns to.
- `ConnectionLabels` with English defaults, including the `not_confirmed` reason ("Nothing changed") for a
  return address whose claim the live list does not back.

## 0.2.0 - unreleased
- `WantedSet(id, provider, label, scopes, granted)` with `fromJson`.
- `ConnectionList(connections, wanted)` with `fromJson` (bare array or `{connections, wanted}`); `wanted` defaults to `const []`.
- `ConnectionsApi.listAll()` (the whole answer), `ConnectionsApi.wanted()`; `list()` is unchanged.
- `ConnectionsApi.startUrl(..., set:)` adds the `set` query parameter (a wanted set id).
- `ConnectionReturn.attempt` read from the `attempt` query parameter; `cleaned` drops `attempt` and `code` too.
- The pubspec version is bumped to 0.2.0 by the director (builders do not edit pubspecs).
