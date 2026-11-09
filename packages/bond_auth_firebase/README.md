# bond_auth_firebase

Firebase adapter for `bond_auth`: `FirebaseIdTokenSource` (e-mail and password, Google, Apple, linking), the `failureFor` error table, runtime initialisation from `GET /auth/providers`, and `AppleNonce`.

```dart
final providers = await gateway.providers();
final config = providers.firebase;
if (config != null) await initFirebaseFromRuntimeConfig(config, isWeb: kIsWeb);
final source = FirebaseIdTokenSource(google: myGoogleDriver, appleFetcher: myAppleFetcher);
```

- No generated options file: the public client config comes from the server at runtime.
- `FirebaseAuth` sits behind `FirebaseAuthLike`, so tests use a fake and never start Firebase.
- The app supplies the Google and Apple packages through `GoogleSignInDriver` and `AppleCredentialFetcher`.
