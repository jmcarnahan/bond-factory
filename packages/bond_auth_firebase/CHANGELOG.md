# Changelog

## 0.1.0 - unreleased
- `FirebaseIdTokenSource` implements `IdTokenSource` and `FederatedSignIn`, over a `FirebaseAuthLike` / `FirebaseUserLike` seam (`FirebaseAuthAdapter` wraps the real `FirebaseAuth`).
- `FederatedSignIn`, `GoogleSignInDriver` (the app owns the Google package), `AppleCredentialFetcher` and `AppleCredentialData`.
- `failureFor(FirebaseAuthException)` code table (`internal-error` reads as network).
- `currentIdToken` returns null only for user-disabled, user-not-found, user-token-expired and invalid-user-token; every other provider error is thrown so a transient fault never reads as signed out.
- `initFirebaseFromRuntimeConfig(config, isWeb:)` and `firebaseOptionsFor`: starts Firebase from the server's public config, once, only when no app exists; a failure is not remembered.
- `AppleNonce` (random nonce and its SHA-256).
