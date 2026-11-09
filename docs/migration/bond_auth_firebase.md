# Migrating to bond_auth_firebase

`bond_auth_firebase` is the Flutter adapter: `FirebaseIdTokenSource` (implements `IdTokenSource` and `FederatedSignIn`), `failureFor`, `initFirebaseFromRuntimeConfig`, `AppleNonce`. Few-shot reference: `demos/sdk_demo` runs in mock mode and uses `FakeIdTokenSource` from `bond_auth` instead; the adapter is unit tested with a fake `FirebaseAuthLike`. Legend: `docs/migration/README.md`.

## 1. What it replaces

**App A (avalon).** `flutterui/packages/avalon_core/lib/src/auth/real_id_token_source.dart` (245) and `apple_nonce.dart` (44). `firebase_options.dart` goes away (see section 4).

**App P (paga).** `pt_core/lib/src/auth/real_id_token_source.dart` (134, the e-mail only twin) and the placeholder options file.

**App S (sbel).**
- Web: `flutterui/lib/data/services/firebase_id_token_source.dart` (134). Its `prepare()` fetched `/auth/providers` and called `Firebase.initializeApp` once; that is now `AuthProviders.firebase` plus `initFirebaseFromRuntimeConfig(config, isWeb: true)`.
- Mobile: `RealFirebaseGateway` in `core/auth/firebase_gateway.dart`; S's gateway sent the e-mail and password itself, now it is `FirebaseAuthGateway(source: FirebaseIdTokenSource())` from `bond_auth`.

## 2. The adapter

- A: `RealIdTokenSource` becomes `FirebaseIdTokenSource(google: ..., appleFetcher: ...)`.
- A called `GoogleSignIn.instance` inside the class. The adapter does not depend on a Google package: write a `GoogleSignInDriver` (prepare with the web client id, `authenticate()` returning Google's id token, `signOut()`) in the app and pass it in. Map `GoogleSignInException` to `AuthFailure` in the driver (A's `googleFailureFor`).
- `AppleCredentialFetcher` and `AppleCredentialData` keep their shape; `AppleNonce` is identical.
- P: use `FirebaseIdTokenSource()` with no Google or Apple driver.
- Initialise once at start-up, before the first sign-in:
  `final p = await gateway.providers(); final c = p.firebase; if (c != null) await initFirebaseFromRuntimeConfig(c, isWeb: kIsWeb);`
  It returns false (and starts nothing) when this platform's block is incomplete; it skips `Firebase.initializeApp` when an app already exists; a failure is retried on the next call.

## 3. Call-site changes

- Google and Apple: `source.signInWithGoogle()` returns the Firebase id token; pass it to `gateway.signInWithIdToken`. Same for `signInWithApple()` and `signInWithGoogleCredential(credential)` (web button).
- `linkedProviders()` returns a `List<String>`.
- `prepareGoogle([webClientId])` takes the web client id from `AuthProviders.googleWebClientId`.
- `RealIdTokenSource.failureFor` is the top-level `failureFor`.
- S: `FirebaseFailureReason` (5 values) folds into `AuthFailureReason`.

## 4. Data

No database change. Env and config:
- Server env: `FIREBASE_PROJECT_ID`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_WEB_API_KEY`, `FIREBASE_WEB_APP_ID`, `FIREBASE_IOS_API_KEY`, `FIREBASE_IOS_APP_ID`, `FIREBASE_IOS_BUNDLE_ID` (all public client values), exposed through `GET /auth/providers`.
- No `--dart-define` for Firebase and no generated options file in the client.
- Dependencies in the app: `firebase_core`, `firebase_auth` come with the adapter; add `google_sign_in` / `sign_in_with_apple` in the app only if it uses them.

## 5. Acceptance

- [ ] Web and phone sign in by e-mail against a server with Firebase configured; no `firebase_options.dart` in the tree.
- [ ] A wrong password and an unknown address both show `wrongCredentials`.
- [ ] A cancelled Google or Apple sheet shows `cancelled`, not an error.
- [ ] Linking Google twice shows `alreadyLinked`.
- [ ] Sign-out signs the Google SDK out only when it was started.
- [ ] `grep -r firebase_options` finds nothing in the app.

## 6. Known gaps

- Two failure codes changed: `credential-already-in-use` now maps to `alreadyLinked` (A mapped it to `accountExistsWithDifferentCredential`).
- The adapter has no Google package dependency; each app keeps its own `GoogleSignInDriver`.
