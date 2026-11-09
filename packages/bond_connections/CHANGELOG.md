# Changelog

## 0.1.0 - unreleased
- `ConnectionStatus` (fromJson/toJson), `ConnectionPhase` (disconnected, connected, needsReconnect; named so to
  avoid Flutter's `ConnectionState`).
- `ConnectionsApi` (`list`, `startUrl`, `disconnect`), `DemoConnectionsApi` (`simulateExpiry`).
- `ConnectionReturn.parse` / `cleaned` for the address the browser returns to.
- `ConnectionLabels` with English defaults, including the `not_confirmed` reason ("Nothing changed") for a
  return address whose claim the live list does not back.
