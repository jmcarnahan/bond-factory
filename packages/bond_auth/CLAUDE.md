# bond_auth
Role: Pure Dart auth contracts: id-token source seam, token stores, session, capability policy, gateways, providers.

## Key files
- `lib/src/gateway.dart` (contract + `renewalHook`), `demo_gateway.dart`, `firebase_gateway.dart` (single-flight refresh), `gateway_support.dart`.
- `lib/src/refresh_token_store.dart` (two-slot refresh storage), `rotation_ids.dart` (`rotation_id` per rotation; `gateway_support.dart` writes refresh first, ends sessions on final 401 codes).
- `lib/src/id_token_source.dart`, `auth_failure.dart`, `token_store.dart`, `session.dart`, `capability_policy.dart`, `providers.dart`.

## Commands
- `make test T=test/gateway_test.dart`
- `make analyze`

## Rules
- No Flutter imports. `SessionRefresh` lives in bond_api; re-export it, never redefine.
- Refresh: null = offline (keep session), `AuthFailure` (except reason network, which is offline) or another person = rejected; never store a session for another person.
- Tests use `MockClient` (`test/support.dart`), not bond_test_support (Flutter).
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
