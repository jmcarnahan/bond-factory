# bond_signin_ui

Sign-in screen, buttons, scope-ask card, the system-browser port and a secure refresh-token store for the bond
apps. Built on `bond_signin`, `bond_ui` and `bond_connections`. No dialogs, sheets or snack bars: errors and the
break-glass form show inline. No embedded web views (Google refuses them); the sign-in sheet that appears on a
phone is the operating system's, an RFC 8252 requirement.

| Name | What it is |
|---|---|
| `BondSignInScreen` | Title, one button per `providers.signin`, invite-only line, inline error strip, break-glass link |
| `BondSignInButtons` | The buttons alone |
| `BondScopeAskCard` | Ungranted `WantedSet`s with one Allow button each; nothing when all are granted |
| `BrowserAuth`, `defaultBrowserAuth()` | The system-browser port; the implementation is chosen at compile time |
| `replaceAddress(Uri)` | Web: clean the return query out of the address bar; elsewhere a no-op |
| `NativeReturn.choose(...)` | https return on devices that support it, else the custom scheme |
| `SecureRefreshTokenStore` | `RefreshTokenStore` over `flutter_secure_storage`, key `<appKey>.bond_refresh_token` |

Semantics ids: `sdk.signin.<provider>`, `sdk.signin.error`, `sdk.signin.break-glass`, `sdk.scopes.ask-<set id>`
(each prefix is a constructor argument).

## Web recipe
1. `final auth = OidcAuthGateway(api: api, tokens: tokens)` (no refresh store: the cookie carries it) and an
   `ApiClient` whose http client sends credentials (a `BrowserClient` with `withCredentials = true`).
2. Button pressed: `final url = await SignInApi(api).startWeb(id, redirectTo: origin);` then
   `await defaultBrowserAuth().run(url, callback: Uri.parse(origin))`. The window navigates; `run` never returns.
3. On the next load: `final r = SignInReturn.parse(Uri.base);` then `replaceAddress(SignInReturn.cleaned(Uri.base))`.
   `SignInReturnKind.ok` calls `auth.completeWeb()`; `error` shows `BondSignInScreen(errorCode: r.reason)`.

## Phone recipe
1. Inject `SecureRefreshTokenStore(appKey: 'app-x')` as `refreshTokens` of `OidcAuthGateway`; this is the only
   storage code the app has. Delivery (cookie or body) follows the store, never `Platform`.
2. Choose the return, then start with that same URL:
   ```dart
   final ret = NativeReturn.choose(
     httpsReturn: Uri.parse('https://<api>/app/return/$id'),
     schemeReturn: Uri.parse('<reverse.domain>://return/$id'),
     httpsSupported: <iOS 17.4+ or Android>, // the app decides; the SDK never reads the platform
   );
   final (attempt, url) = await SignInApi(api).startNative(id, returnUrl: ret); // sent as redirect_to unchanged
   ```
   Keep `attempt` (`attempt.toJson()` survives a cold start, in secure storage only).
3. `final back = await defaultBrowserAuth().run(url, callback: ret);`
4. `final r = SignInReturn.parse(back); if (!r.matches(attempt)) return;` (a return for another attempt is
   ignored), then `await auth.completeNative(attempt, r.code!)` or show `r.reason`.

## Platform minimums
- `flutter_web_auth_2` 5.1.0 builds for iOS 11, but an https (universal link) return works only at runtime on iOS
  17.4 and later; below that use the scheme return. Android: https returns need App Links.
- `flutter_secure_storage` 11.2 needs iOS 13.
- An identity-only app still pulls `bond_connections` and both plugins; that is by design.

## iOS and Android setup in the app
- iOS, Associated Domains entitlement (`Runner.entitlements`):
  `com.apple.developer.associated-domains` = `applinks:<api host>` and `webcredentials:<api host>`. The server
  serves `/.well-known/apple-app-site-association` with no redirect. A private dev host needs the
  `?mode=developer` suffix. For the scheme fallback add the scheme to `CFBundleURLTypes`.
- Android, `AndroidManifest.xml`: `android:taskAffinity=""` on the activity, and the plugin's `CallbackActivity`
  with an intent filter `action VIEW`, categories `DEFAULT` and `BROWSABLE`, `android:autoVerify="true"`, data
  scheme `https`, host `<api host>`, pathPrefix `/app/return`. The server serves `/.well-known/assetlinks.json`.
  For the scheme fallback, a second filter with data scheme `<reverse.domain>`.
- Values (team id, bundle id, certificate fingerprints, hosts) live in the app's environment, never in this repo.

## Scope asks
`BondScopeAskCard(wanted: await connections.wanted(), onAsk: (s) => ..., labels: labels)` where `onAsk` starts the existing
connect flow for the set (`ConnectionsApi.startUrl(provider, set: s.id)`), then reload the list.

Tests: `make test T=test/widgets_test.dart`. They pump at 1280x800 and 390x844 and end with `expectNoOverlays`.
