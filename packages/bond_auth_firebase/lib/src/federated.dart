/// The Google and Apple half of sign-in: the part whose signatures carry
/// Firebase credential types, so it cannot live in the pure Dart `bond_auth`.
library;

import 'package:firebase_auth/firebase_auth.dart' show OAuthCredential;

abstract interface class FederatedSignIn {
  /// Starts the Google SDK (the web build needs [webClientId]). A failed start
  /// is not remembered.
  Future<void> prepareGoogle([String? webClientId]);

  /// Shows Google's account chooser, signs in, and returns the Firebase id token.
  Future<String> signInWithGoogle();

  Future<String> signInWithGoogleCredential(OAuthCredential credential);

  /// Links a Google account to the signed-in user.
  Future<void> linkGoogle();

  Future<void> linkGoogleCredential(OAuthCredential credential);

  /// Sign in with Apple; returns the Firebase id token.
  Future<String> signInWithApple();
}

/// What the app's Google sign-in package does. The app owns that package; this
/// package only needs a Google id token from it.
abstract interface class GoogleSignInDriver {
  Future<void> prepare(String? webClientId);

  /// Shows the chooser and returns Google's id token. Throws `AuthFailure`
  /// (`cancelled`, `notConfigured`, ...) on failure.
  Future<String> authenticate();

  Future<void> signOut();
}

/// What the Apple sheet returned: the signed identity token and, on the first
/// sign-in only, the person's name.
class AppleCredentialData {
  const AppleCredentialData({required this.identityToken, this.givenName, this.familyName});

  final String? identityToken;
  final String? givenName;
  final String? familyName;
}

/// Shows Apple's sheet with the already hashed nonce. The app supplies it
/// (it owns the Sign in with Apple package) and throws `AuthFailure` with
/// `cancelled` when the person backs out.
typedef AppleCredentialFetcher = Future<AppleCredentialData> Function(String hashedNonce);
