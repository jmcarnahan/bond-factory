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

## 0.2.0 - unreleased
- `RefreshTokenStore` (load, save, clear, reload), `InMemoryRefreshTokenStore`, `NoRefreshTokenStore` (web: the cookie carries the token).
- `AuthSession.refreshToken` (nullable), read from the answer's `refresh_token` by `sessionFromAuthBody`.
- `GatewayBase` and `sessionFromAuthBody`, `asAuthFailure`, `isOfflineFailure`, `sessionEndCodes` are now exported.
- `GatewayBase` takes `refreshTokens` (default `NoRefreshTokenStore()`), `onSessionEnded` and `rotationIds`;
  `FirebaseAuthGateway` and `DemoAuthGateway` pass them through. Existing constructors compile unchanged.
- `accept` and renewal save the new refresh token before the access token; the refresh store is reloaded before every rotation.
- A 401 with `refresh_reused`, `refresh_expired`, `refresh_revoked`, `session_revoked` or `invalid_handoff` in a
  renewal clears both stores, sets `lastEndReason`, calls `onSessionEnded(code)` and rejects; offline keeps both.
- `endServerSession` sends the stored refresh token in the logout body and clears both stores.
- `RotationIds` (`current`, `succeeded()`): the random `rotation_id`, reused on a retry, new after a success.
- `LiveTokenForgetter(..., refreshTokens:)` clears the second slot.
- `SignInProvider(id, label)`; `AuthProviders.signin`, `breakGlass`, `defaultFlow` read from `signin`, `break_glass`, `default_flow` (absent keys give `[]`, false, `firebase`); `signinById(id)`.
- `RefreshTokenStore.loadRotation()` / `saveRotation(String?)` (interface addition): the in-flight rotation id is saved before every rotate, adopted on cold start (`RotationIds.adopt`) and cleared after a stored success, so a crash after the server rotated retries with the same id.
- Store writes in `accept` and renewal are guarded: a failing write keeps the in-memory session and calls `onStorageFailure(error)`; the rotation id is then NOT retired.
- The pubspec version is bumped to 0.2.0 by the director (builders do not edit pubspecs).
