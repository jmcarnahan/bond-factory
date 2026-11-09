# bond_signin
Role: pure-Dart client of the direct sign-in routes (no Flutter, no dart:io). UI and the system browser live in bond_signin_ui.

## Key files
- `lib/src/sign_in_api.dart` SignInApi (alias SignInClient): startWeb, startNative, redeem, providers
- `lib/src/sign_in_attempt.dart` attempt id, device secret and challenge (Random.secure, package:crypto)
- `lib/src/sign_in_return.dart` parse and clean the return address
- `lib/src/oidc_gateway.dart` OidcAuthGateway over GatewayBase
- `lib/src/labels.dart` SignInLabels (English defaults)

## Commands
- `make test T=test/oidc_gateway_test.dart`
- `make analyze`

## Rules
- Imports no Flutter and no dart:io; delivery (cookie or body) is decided by the injected RefreshTokenStore.
- Never log tokens, device secrets or codes.
- No codegen; hand-write fromJson. Siblings by pubspec `path:` only.
- Barrel + CHANGELOG.md updated on every public API change. 300-line soft cap per source file.
