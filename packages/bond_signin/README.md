# bond_signin

Direct Google and Microsoft sign-in client for the bond apps. Pure Dart: no Flutter, no `dart:io`. The widgets and
the system browser live in `bond_signin_ui`. The server routes are in `libs/bond_signin`.

| Name | What it is |
|---|---|
| `SignInAttempt` | Native attempt: `id` (16 bytes hex), `deviceSecret` (32 bytes base64url), `deviceChallenge` (sha256 hex). `generate()`, `toJson`/`fromJson` to survive a cold start |
| `SignInReturn` | `parse(Uri)` into `ok`, `error` (with `reason`), `native` (`attempt`, `code` or error), `none`; `matches(pending)`; `cleaned(Uri)` |
| `SignInApi` (alias `SignInClient`) | `startWeb`, `startNative`, `redeem`, `providers` |
| `OidcAuthGateway` | `GatewayBase` for direct sign-in: `completeWeb`, `completeNative`, renewal, `signOut` |
| `SignInLabels` | English strings: title, `continueWith`, invite-only, break-glass, one message per code |

## Web
The nonce cookie must be set by a POST the person's own page sends, so there is no start link:
```dart
final url = await SignInApi(api).startWeb('google', redirectTo: origin); // POST sets the cookie
// navigate the window to url (bond_signin_ui: defaultBrowserAuth().run)
// next load: SignInReturn.parse(Uri.base).kind == SignInReturnKind.ok
final session = await OidcAuthGateway(api: api, tokens: tokens).completeWeb(); // POST /auth/refresh {}
```
Use no refresh store (the default `NoRefreshTokenStore`): delivery is the HttpOnly cookie. The ApiClient's http
client must send credentials, and the client is built with `ApiClient(isWeb: true, ...)` so a blocked cross-origin
call reads as a CORS problem. The app must use the path URL strategy (`usePathUrlStrategy()`): with fragment
routes (`/#/home`) the return query is lost.

`OidcAuthGateway` takes `authPrefix` (default `/auth`) and `SignInApi` takes `prefix` when the routes are mounted
elsewhere (`'/api/v1/auth'`); one `authPrefix` drives every path of the gateway, logout included.

## Phone
```dart
final (attempt, url) = await SignInApi(api).startNative('google', returnUrl: ret); // ret = NativeReturn.choose(...) from bond_signin_ui
// system browser returns; ignore it unless SignInReturn.parse(back).matches(attempt)
final session = await gateway.completeNative(attempt, ret.code!); // redeem, refresh token saved first
```
Give the gateway a real `RefreshTokenStore` (`SecureRefreshTokenStore` in `bond_auth_secure_storage`). A store that holds a
token means body delivery; renewal posts `{refresh_token, rotation_id, delivery: "body"}`. A lost answer retries
with the same rotation id. A final refusal (`refresh_reused`, `refresh_expired`, `refresh_revoked`) clears both
tokens, sets `lastEndReason` and calls `onSessionEnded(code)`.

## Rules
- A `SignInAttempt` holds the device secret: persist it (`toJson`) only in secure storage, never in preferences.
- Tokens, device secrets and codes are never logged; `toString` of an attempt or return leaves them out.
- E-mail and password methods of `OidcAuthGateway` throw `UnsupportedError`; break-glass uses the Firebase gateway.
- A return whose `attempt` is not the pending one must be ignored (a lured victim's browser).

Tests (no Flutter, `http` MockClient fakes): `make test T=test/oidc_gateway_test.dart`.
