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

See `demos/sdk_demo` (auth page) and `services/sdk_example` (`routes/auth.py`).
