# Migrating to bond_auth

`bond_auth` is pure Dart: token stores, `AuthSession`, `AuthFailure`, the id-token seam, gateways, capability policy, providers parsing. Few-shot reference: `demos/sdk_demo/lib/src/example_api.dart` (wiring) and `pages/auth_page.dart`, with `services/sdk_example/sdk_example/routes/auth.py` as the server. Legend: `docs/migration/README.md`.

Contracts: `docs/contracts/auth.md`.

## 1. What it replaces

**App A (avalon).** In `flutterui/packages/avalon_core/lib/src/`:
- `auth/auth_gateway.dart` (340): `AuthFailureReason`, `AuthFailure`, `IdTokenSource`, `NotConfiguredIdTokenSource`, `SessionBelongsToAnotherPerson`, `AuthGateway`, `DemoAuthGateway`, `FirebaseAuthGateway`.
- `auth/token_store.dart` (118): `TokenSource`, `TokenStore`, `InMemoryTokenStore`, `TokenStoreException`.
- `models/capability.dart` (33): becomes `CapabilityPolicy` / `ClaimListPolicy`.
- Stays in A: `PrefsTokenStore` (shared preferences adapter), `tab_identity_store.dart`, the app's sign-in screens.
- Names survive, so most call sites only change the import.

**App P (paga).** Replaces the twins `pt_core/lib/src/auth/{auth_gateway 213, token_store 60}.dart`. P's body has `company` beside `user`: read it from `AuthSession.user` siblings in an app adapter, or keep it in the app's own response model.

**App S (sbel).** Replaces `mobile/crm_proposals/lib/core/auth/{firebase_gateway 211, token_store 110}.dart` and the single-flight in `sync/app/auth_bridge.dart` (`SessionRefresher`; the gateway is single-flight now). `auth_controller.dart` (state machine, gates) stays app-side and calls the gateway.
Dialect differences S must resolve first (server side, see `bond_auth_py`):
- `sub` is the e-mail today; the contract has `sub` = user id plus `capabilities` and `iat`. `AuthSession.fromToken` throws when `sub` is missing.
- `role`, `is_admin`, `provider` claims: map to capabilities in S's `extra_claims`, then `ClaimListPolicy`.
- Error bodies `{"error_code": "NOT_INVITED", "detail": "..."}` become `{"detail": {"code": "not_invited", ...}}`; 409 for identity mismatch becomes 403 `identity_mismatch`.
- No refresh and no revocation today: add `POST /auth/refresh` and `sessions_valid_after` or keep `onUnauthorized` unset.
- `FirebaseFailureReason` collapses into `AuthFailureReason`; `FirebaseClientConfig.fromProviders` becomes `FirebaseRuntimeConfig.fromProviders` (the web block needs `api_key`, `app_id`, `auth_domain`, `messaging_sender_id`).

## 2. The adapter

- A `TokenStore` over the app's storage (shared preferences, secure storage). Wrap it in `ReloadableTokenStore` when the store is slow or shared between tabs, and give it a `LiveTokenForgetter` wired to `ApiClient.onSessionExpired`, `onSessionRevoked`, `onDeactivated`.
- Compose: one `ApiClient(tokens: store)`, one gateway, `api.onUnauthorized = renewalHook(gateway, expectedUserId: ...)`.

## 3. Call-site changes

- `AuthGateway.linkedProviders` returns `List<String>`, not `Set<String>`.
- Google and Apple methods left the gateway: call `FederatedSignIn` on the source (`bond_auth_firebase`), then `gateway.signInWithIdToken(idToken)`.
- `refreshSession` returns null only when the server or provider cannot answer (5xx except 501, 408, 429, no answer) or the person signed out while it ran. A person with no provider session now throws `AuthFailure(wrongCredentials)` instead of returning null, so the hook reads it as `rejected`.
- `signInWithIdToken(idToken, {signIn})`: `signIn: false` sends `sign_in: false`.
- `ReloadableTokenStore` is a wrapper class; A's `peekStored` / `adoptStored` and `forgetLive` stay on A's prefs store.
- `AuthSession` gains `user` (the server's `user` object); build the app's user model from it.

## 4. Data

No database change. Config:
- No generated options file: the app calls `GET /auth/providers` and passes `AuthProviders.firebase` to `initFirebaseFromRuntimeConfig`. Delete `firebase_options.dart` from the build.
- Provider flags (`demo`, `email_password`, `google`, `apple`, `mock`) come from the same call.

## 5. Acceptance

- [ ] `bond_auth` imports replace the files above; the old files are deleted.
- [ ] Two concurrent 401s cause one `POST /auth/refresh`.
- [ ] A renewal for another person leaves the stored token unchanged.
- [ ] `not_invited`, `apple_relay`, `deactivated` reach the screens as `AuthFailure` reasons.
- [ ] Offline refresh keeps the session; a 401 from `/auth/refresh` signs out.
- [ ] The app's auth tests pass unchanged except imports.

## 6. Known gaps

For A and P, none beyond the call-site changes in section 3. For S, the dialect differences listed under App S in section 1 are the gaps; S migrates its server contract first.
