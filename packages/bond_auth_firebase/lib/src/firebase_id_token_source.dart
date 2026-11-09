/// Firebase-backed identity provider for `bond_auth`.
library;

import 'package:bond_auth/bond_auth.dart';
import 'package:firebase_auth/firebase_auth.dart' show AppleAuthProvider, AppleFullPersonName, FirebaseAuthException, GoogleAuthProvider, OAuthCredential;

import 'apple_nonce.dart';
import 'federated.dart';
import 'firebase_failure.dart';
import 'firebase_seam.dart';

/// The Firebase user is only the identity. Authorization comes from the
/// session the backend mints from the id token. Needs an initialised Firebase
/// app unless [auth] is a fake.
class FirebaseIdTokenSource implements IdTokenSource, FederatedSignIn {
  FirebaseIdTokenSource({FirebaseAuthLike? auth, this.google, this.appleFetcher}) : _auth = auth;

  final FirebaseAuthLike? _auth;
  FirebaseAuthLike? _default;
  FirebaseAuthLike get _a => _auth ?? (_default ??= FirebaseAuthAdapter());

  /// The app's Google sign-in package behind a small interface. Null: no Google.
  final GoogleSignInDriver? google;

  /// Shows Apple's sheet. Null on builds without Sign in with Apple.
  final AppleCredentialFetcher? appleFetcher;

  static const _signedOutCodes = {'user-disabled', 'user-not-found', 'user-token-expired', 'invalid-user-token'};

  Future<void>? _googleReady;

  @override
  bool get isConfigured => true;

  @override
  Future<String?> currentIdToken({bool forceRefresh = false}) async {
    try {
      return await _a.currentUser?.getIdToken(forceRefresh: forceRefresh);
    } on FirebaseAuthException catch (e) {
      // A disabled or deleted account, or a revoked login, cannot mint a token:
      // same as signed out. Anything else (rate limit, network, internal error)
      // is transient: the caller must not read it as "no session".
      if (_signedOutCodes.contains(e.code)) return null;
      throw failureFor(e);
    }
  }

  @override
  Future<void> signInWithEmail(String email, String password) async {
    try {
      final user = await _a.signInWithEmailAndPassword(email.trim(), password);
      if (user == null) throw const AuthFailure(AuthFailureReason.other);
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  @override
  Future<void> sendPasswordReset(String email) async {
    try {
      await _a.sendPasswordResetEmail(email.trim());
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  @override
  Future<void> changePassword(String current, String next) async {
    final user = _a.currentUser;
    final email = user?.email;
    if (user == null || email == null || email.isEmpty) {
      throw const AuthFailure(AuthFailureReason.notConfigured);
    }
    try {
      await user.reauthenticateWithPassword(email, current);
      await user.updatePassword(next);
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  @override
  Future<List<String>> linkedProviders() async {
    // An admin may have given this person a password since they signed in:
    // read the account again, and fall back to what the device holds.
    try {
      await _a.currentUser?.reload();
    } catch (_) {}
    return List.of(_a.currentUser?.providerIds ?? const <String>[]);
  }

  @override
  Future<void> signOut() async {
    await _a.signOut();
    // Let the next person pick their own Google account.
    if (_googleReady != null) {
      try {
        await google?.signOut();
      } catch (_) {}
    }
  }

  @override
  Future<void> prepareGoogle([String? webClientId]) {
    final driver = google;
    if (driver == null) return Future.error(const AuthFailure(AuthFailureReason.notConfigured));
    // A failed start is not remembered: the next try starts again.
    return _googleReady ??= driver.prepare(webClientId).catchError((Object e) {
      _googleReady = null;
      throw e is AuthFailure ? e : const AuthFailure(AuthFailureReason.notConfigured);
    });
  }

  Future<OAuthCredential> _googleCredential() async {
    await prepareGoogle();
    final idToken = await google!.authenticate();
    if (idToken.isEmpty) throw const AuthFailure(AuthFailureReason.other);
    return GoogleAuthProvider.credential(idToken: idToken);
  }

  @override
  Future<String> signInWithGoogle() async => signInWithGoogleCredential(await _googleCredential());

  @override
  Future<String> signInWithGoogleCredential(OAuthCredential credential) async {
    try {
      return await _tokenOf(await _a.signInWithCredential(credential));
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  @override
  Future<void> linkGoogle() async => linkGoogleCredential(await _googleCredential());

  @override
  Future<void> linkGoogleCredential(OAuthCredential credential) async {
    final user = _a.currentUser;
    if (user == null) throw const AuthFailure(AuthFailureReason.other);
    try {
      await user.linkWithCredential(credential);
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  @override
  Future<String> signInWithApple() async {
    final fetch = appleFetcher;
    if (fetch == null) throw const AuthFailure(AuthFailureReason.notConfigured);
    final credential = await appleCredential(fetch, AppleNonce.generate());
    try {
      return await _tokenOf(await _a.signInWithCredential(credential));
    } on FirebaseAuthException catch (e) {
      throw failureFor(e);
    }
  }

  /// Apple's sheet gets the hashed nonce; Firebase's credential gets the raw
  /// one. Public so a test can check the pairing without a Firebase app.
  static Future<OAuthCredential> appleCredential(AppleCredentialFetcher fetch, AppleNonce nonce) async {
    final apple = await fetch(nonce.hashed);
    final token = apple.identityToken;
    if (token == null || token.isEmpty) throw const AuthFailure(AuthFailureReason.other);
    return AppleAuthProvider.credentialWithIDToken(
      token,
      nonce.raw,
      AppleFullPersonName(givenName: apple.givenName, familyName: apple.familyName),
    );
  }

  Future<String> _tokenOf(FirebaseUserLike? user) async {
    final token = await user?.getIdToken();
    if (token == null || token.isEmpty) throw const AuthFailure(AuthFailureReason.other);
    return token;
  }
}
