# sdk_demo
Role: Flutter web harness for every bond SDK package. Never shipped.

## Commands
- `make test T=test/smoke_test.dart`
- `make analyze`
- `make serve-web` (debug web-server on :8078)

## Sign-in
- `/auth` uses `bond_signin(_ui)`: `DemoSession.signInWith` -> fake consent page on the example -> `/auth?signin=ok|error`.
  Navigation helpers (`defaultBrowserAuth`, `replaceAddress`) come from `bond_signin_ui`; do not copy them here.
- Web delivery is the HttpOnly cookie (`NoRefreshTokenStore`); tests use `InMemoryRefreshTokenStore`.
- `sdk.signin.*`, `sdk.auth.*`, `sdk.scopes.ask-<set>` ids are walked by docs/test/WEB.md "Sign-in walk".

## Rules
- No popups, dialogs or modal sheets; show state inline.
- No codegen.
- Depend on packages by pubspec `path:` only.
- 300-line soft cap per source file.
