# bond_auth_firebase
Role: Firebase adapter for bond_auth: token source, runtime init, Apple nonce.

## Key files
- `lib/src/firebase_id_token_source.dart`, `firebase_seam.dart` (the `*Like` fakes seam), `federated.dart`.
- `lib/src/firebase_failure.dart` (`failureFor`), `firebase_init.dart`, `apple_nonce.dart`.

## Commands
- `make test T=test/firebase_id_token_source_test.dart`
- `make analyze`

## Rules
- No popups, dialogs or modal sheets; show state inline.
- Tests use the fake seam; never call `Firebase.initializeApp` for real.
- Init is memoised on success only; failure must not be cached.
- No codegen; hand-write fromJson.
- Barrel + CHANGELOG.md updated on every public API change.
- 300-line soft cap per source file.
