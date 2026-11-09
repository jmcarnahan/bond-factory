# bond_connections_ui
Role: Connection card, list and return banner built on bond_ui and bond_connections.

## Key files
- `lib/src/connection_card.dart` (state chip, buttons by state, two-step disconnect), `connections_list.dart`, `return_banner.dart`.

## Commands
- `make test T=test/connections_ui_test.dart`
- `make analyze`

## Rules
- No popups, dialogs or modal sheets; show state inline (disconnect uses `BondConfirm`).
- `semanticsId` is a prefix; ids are `<prefix>.<part>-<provider>`.
- Strings come from `ConnectionLabels`; colours from bond_ui tokens.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
