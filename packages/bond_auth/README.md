# bond_auth

Pure Dart auth contracts for the bond app family: the identity-provider seam, token stores, session decoding, capability policy and the gateways that talk to the server's `/auth/*` routes. The wire contract is in `docs/contracts/auth.md`.

```dart
final tokens = InMemoryTokenStore();
final api = ApiClient(baseUrl: base, http: http.Client(), tokens: tokens);
final gateway = FirebaseAuthGateway(api: api, tokens: tokens, source: idTokenSource);
api.onUnauthorized = renewalHook(gateway); // one silent renewal per 401
final session = await gateway.signInWithEmail(email, password);
```

- `refreshSession` is single-flight: concurrent callers share one `POST /auth/refresh`.
- It returns null when the server could not be reached, and throws `AuthFailure` when refused, or `SessionBelongsToAnotherPerson` (nothing stored) when the new session is for someone other than `expectedUserId`.
- Google and Apple sign-in live in `bond_auth_firebase`.
- `FakeIdTokenSource` mints `mock:<email>` id tokens for tests and the demo.

## Refresh sessions (native and web)

The server can issue a rotating refresh token beside the access token. Pass a `RefreshTokenStore` to any gateway:

```dart
final gateway = FirebaseAuthGateway(
  api: api, tokens: tokens, source: idTokenSource,
  refreshTokens: InMemoryRefreshTokenStore(), // native: keep it in the Keychain or Keystore
  onSessionEnded: (code) => showSignIn(reason: code), // refresh_reused, refresh_expired, ...
);
```

- `NoRefreshTokenStore` (the default) means the HttpOnly cookie carries the refresh token, as on web. Delivery
  follows the store, never the platform.
- `accept` and every renewal save the NEW refresh token BEFORE the access token (write-ahead), then the access token.
- `reload()` on the refresh store runs before every rotation, so two isolates share one token.
- A 401 with `refresh_reused`, `refresh_expired`, `refresh_revoked`, `session_revoked` or `invalid_handoff` during a
  renewal clears both stores, sets `lastEndReason`, calls `onSessionEnded(code)` and the hook reports `rejected`.
  Network errors and 5xx keep both tokens (offline).
- `RotationIds.current` is the `rotation_id` to send with a rotation. It stays the same on a retry and changes after a
  stored success. A gateway that rotates sends it; the base class resets it.
- Crash safety: the rotation id is saved to the store before each rotate, adopted by the next run, and cleared only after the new tokens are stored. A crash after the server rotated therefore retries as a lost answer, not as reuse. A failing store write keeps the session in memory and calls `onStorageFailure`.
- `GatewayBase` is exported so another package can build a gateway on it (`bond_signin` does).
- `LiveTokenForgetter(store, refreshTokens: ...)` clears both slots.
- `AuthProviders.signin`, `breakGlass`, `defaultFlow`, `signinById(id)` read `GET /auth/providers`.

See `demos/sdk_demo` (auth page) and `services/sdk_example` (`routes/auth.py`).
