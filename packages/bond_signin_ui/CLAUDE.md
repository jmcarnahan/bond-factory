# bond_signin_ui
Role: sign-in widgets and the system-browser port, built on bond_signin, bond_ui and bond_connections.

## Key files
- `lib/src/sign_in_screen.dart` BondSignInScreen; `sign_in_buttons.dart` BondSignInButtons
- `lib/src/scope_ask_card.dart` BondScopeAskCard (ungranted sets inline, one button each)
- `lib/src/browser/browser_auth.dart` BrowserAuth port; `browser_auth_web.dart` (dart:js_interop); `browser_auth_native.dart` (flutter_web_auth_2); `native_return.dart`
- SecureRefreshTokenStore moved to the `bond_auth_secure_storage` package (this package must not depend on flutter_secure_storage)

## Commands
- `make test T=test/widgets_test.dart`
- `make analyze`

## Rules
- No popups, dialogs, modal sheets or snackbars; show state inline. No embedded web views (system browser only).
- Semantics ids: `sdk.signin.<provider>`, `sdk.signin.error`, `sdk.signin.break-glass`, `sdk.scopes.ask-<set>`.
- Strings come from SignInLabels; colours from bond_ui tokens. Never log tokens.
- No codegen. Barrel + CHANGELOG.md updated on every public API change. 300-line soft cap per source file.
