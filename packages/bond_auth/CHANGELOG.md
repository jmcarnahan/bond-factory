# Changelog

## 0.1.0 - unreleased
- `IdTokenSource` (provider seam, Firebase-type-free), `NotConfiguredIdTokenSource`, `FakeIdTokenSource` (`mock:<email>` tokens).
- `AuthFailure` / `AuthFailureReason`, `AuthFailure.fromApi` (not_invited, apple_relay, deactivated, identity_mismatch, invalid_token, 429, network).
- `TokenStore`, `InMemoryTokenStore`, `ReloadableTokenStore` (wrapper with a synchronous cache), `LiveTokenForgetter`, `TokenStoreException`.
- `AuthSession` (decoded, unverified JWT payload; plus the server's `user` object), `SessionBelongsToAnotherPerson`.
- `CapabilityPolicy`, `ClaimListPolicy(superuser:)`.
- `AuthProviders`, `FirebaseRuntimeConfig` (runtime public client config, no generated options file).
- `AuthGateway`, `DemoAuthGateway`, `FirebaseAuthGateway` (single-flight `refreshSession`), `renewalHook` for `ApiClient.onUnauthorized`.
- Re-exports `SessionRefresh` from bond_api.
- Renewal (both gateways, in `GatewayBase`): single flight per `expectedUserId`; 5xx except 501, 408, 429, no answer, and a network or rate-limited provider error are offline (null, session kept); a 401 or 403 is a refusal.
- A renewal that finishes after `signOut` stores nothing and returns null.
- `AuthFailure.fromApi` keeps the server `code` for every status; 501, `firebase_not_configured` and a 404 (demo off) map to notConfigured; 503 maps to network.
- Gateways expose `exchangeForRefresh` (one unstored exchange) for the shared renewal; apps call `refreshSession`.

## Unreleased
- `RefreshTokenStore` (load, save, clear, reload), `InMemoryRefreshTokenStore`, `NoRefreshTokenStore` (web: the cookie carries the token).
- `AuthSession.refreshToken` (nullable).
- `SignInProvider(id, label)`; `AuthProviders.signin`, `breakGlass`, `defaultFlow` read from `signin`, `break_glass`, `default_flow` (absent keys give `[]`, false, `firebase`).
