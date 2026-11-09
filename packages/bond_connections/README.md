# bond_connections

Status model, API client and return-address parser for the OAuth connections routes (`GET /connections`,
`.../start`, `DELETE /connections/{provider}`). Pure Dart, no Flutter. The widgets are in `bond_connections_ui`.
The server half is `bond_oauth`; the migration notes are in `docs/migration/bond_connections.md`.

| Name | Role |
|---|---|
| `ConnectionStatus` | One row: `provider`, `connected`, `email`, `connectedAt`, `needsReconnect`, `scopes` |
| `ConnectionPhase` | `disconnected`, `connected`, `needsReconnect`; `status.phase` (a needed reconnect wins, even when `connected` is false) |
| `ConnectionsApi(ApiClient, {prefix})` | `list()`, `listAll()`, `wanted()`, `startUrl(provider, {redirectTo, native, set})`, `redeem`, `disconnect(provider)` |
| `WantedSet`, `ConnectionList` | Scope sets the role wants (`id`, `provider`, `label`, `scopes`, `granted`); `listAll()` reads `{connections, wanted}` or a bare array |
| `DemoConnectionsApi` | `simulateExpiry(provider)`; only the example server in fake mode has the route |
| `ConnectionReturn.parse(Uri)` | Reads `connection=connected\|error`, `provider`, `reason`, `code`, `attempt`; null when absent. `cleaned(Uri)` drops them all |
| `ConnectionLabels` | Every string with English defaults; `{provider}` placeholders; plain words for error reasons |

The enum is not called `ConnectionState` because Flutter exports that name.

```dart
final api = ConnectionsApi(apiClient);
final statuses = await api.list();

// Connect: ask for the address, then send the whole browser window to it.
final url = await api.startUrl('google', redirectTo: 'https://app.example.com/connections');
navigateTopLevel(url); // app code: window.location.href = url

// After the provider sends the browser back, the app loads afresh:
final back = ConnectionReturn.parse(Uri.base); // null on an ordinary visit
final fresh = await api.list();                // the truth comes from the server
```

- A role ask: `startUrl(provider, set: wanted.id)` for each `WantedSet` with `granted` false. `list()` still returns the bare list; use `listAll()` or `wanted()` for the sets.
- Nothing is kept across the redirect. Read `list()` again after every return, disconnect or reconnect.
- The start address is a top-level navigation (`/connections/{provider}/go?state=...`). It needs the API session
  cookie, so on web the HTTP client must send credentials to the API origin. Native apps have no such cookie; see
  section 4 of `docs/migration/bond_connections.md`.
- `redirectTo` must be on the server allowlist, or `startUrl` throws `BadRequest`.
- The return parameters stay in the address bar until the app replaces the location; use `ConnectionReturn.cleaned`.
- Errors are the `bond_api` family (`Forbidden` without `connections.manage`, `BadResponse` for an unreadable answer).

Tests: `make test T=test/connections_test.dart`. They use `MockClient` from `package:http/testing.dart`.
