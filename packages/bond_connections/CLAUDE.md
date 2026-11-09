# bond_connections
Role: Pure Dart OAuth connection status model, API client and return-URL parser for the `/connections` routes.

## Key files
- `lib/src/status.dart` (`ConnectionStatus`, `ConnectionPhase`), `api.dart` (`ConnectionsApi`, `DemoConnectionsApi`).
- `lib/src/connection_return.dart` (`ConnectionReturn`), `labels.dart` (`ConnectionLabels`), `wanted.dart` (`WantedSet`, `ConnectionList`).

## Commands
- `make test T=test/connections_test.dart`
- `make analyze`

## Rules
- No Flutter imports. The enum is `ConnectionPhase` because Flutter owns `ConnectionState`.
- Tests use `MockClient` from `package:http/testing.dart`, not bond_test_support (Flutter).
- No state is kept across the browser redirect: the caller reads `list()` again.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
