# bond_auth_secure_storage
Role: SecureRefreshTokenStore, a bond_auth RefreshTokenStore over flutter_secure_storage (phones). Web apps do not use it.

## Key files
- `lib/bond_auth_secure_storage.dart` is the barrel.
- `lib/src/secure_refresh_token_store.dart` SecureRefreshTokenStore (the only file that imports flutter_secure_storage).
- Tests: `test/secure_refresh_token_store_test.dart` over a map-backed fake storage.

## Commands
- `make test T=test/secure_refresh_token_store_test.dart`
- `make analyze`

## Rules
- Depends on bond_auth and flutter_secure_storage only. Do not depend on bond_signin_ui: that package must stay free of this plugin.
- Never log or report a token. A storage failure never throws into a sign-in or a renewal.
- No popups, dialogs, sheets. No intl, riverpod, go_router. No codegen.
- Barrel + CHANGELOG.md updated on every public API change. 300-line soft cap per source file.
