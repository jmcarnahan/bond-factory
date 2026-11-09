import 'package:bond_auth/bond_auth.dart';
import 'package:bond_auth_firebase/bond_auth_firebase.dart';
import 'package:firebase_auth/firebase_auth.dart' show GoogleAuthProvider;
import 'package:flutter_test/flutter_test.dart';

import 'fakes.dart';

class FakeGoogle implements GoogleSignInDriver {
  int prepared = 0;
  int signedOut = 0;
  Object? prepareError;
  String idToken = 'google-id';

  @override
  Future<void> prepare(String? webClientId) async {
    prepared++;
    final e = prepareError;
    if (e != null) throw e;
  }

  @override
  Future<String> authenticate() async => idToken;

  @override
  Future<void> signOut() async => signedOut++;
}

Matcher failure(AuthFailureReason r) => throwsA(isA<AuthFailure>().having((e) => e.reason, 'reason', r));

void main() {
  test('signed out gives no id token; signed in gives one, forced on request', () async {
    final auth = FakeAuth();
    final source = FirebaseIdTokenSource(auth: auth);
    expect(source.isConfigured, isTrue);
    expect(await source.currentIdToken(), isNull);
    final user = auth.currentUser = FakeUser();
    expect(await source.currentIdToken(), 'id-1');
    expect(await source.currentIdToken(forceRefresh: true), 'id-2');
    expect(user.calls, ['getIdToken', 'getIdToken(force)']);
  });

  test('an account that cannot mint a token reads as signed out', () async {
    final user = FakeUser();
    final source = FirebaseIdTokenSource(auth: FakeAuth(user));
    for (final code in ['user-disabled', 'user-not-found', 'user-token-expired', 'invalid-user-token']) {
      user.tokenError = authError(code);
      expect(await source.currentIdToken(forceRefresh: true), isNull, reason: code);
    }
  });

  test('a transient token failure is thrown, never read as signed out', () async {
    final user = FakeUser();
    final source = FirebaseIdTokenSource(auth: FakeAuth(user));
    const expected = {
      'network-request-failed': AuthFailureReason.network,
      'internal-error': AuthFailureReason.network,
      'too-many-requests': AuthFailureReason.rateLimited,
      'something-new': AuthFailureReason.other,
    };
    for (final e in expected.entries) {
      user.tokenError = authError(e.key);
      await expectLater(source.currentIdToken(), failure(e.value), reason: e.key);
    }
  });

  test('signInWithEmail trims the address and maps failures', () async {
    final auth = FakeAuth();
    final source = FirebaseIdTokenSource(auth: auth);
    await source.signInWithEmail('  a@example.com ', 'pw');
    expect(auth.calls, ['signIn:a@example.com']);
    auth.signInError = authError('wrong-password');
    await expectLater(source.signInWithEmail('a@example.com', 'x'), failure(AuthFailureReason.wrongCredentials));
  });

  test('password reset trims and maps failures', () async {
    final auth = FakeAuth();
    final source = FirebaseIdTokenSource(auth: auth);
    await source.sendPasswordReset(' a@example.com');
    expect(auth.calls, ['reset:a@example.com']);
  });

  test('changePassword proves the current password first', () async {
    final user = FakeUser();
    await FirebaseIdTokenSource(auth: FakeAuth(user)).changePassword('old', 'new');
    expect(user.calls, ['reauth:old', 'updatePassword:new']);
  });

  test('changePassword needs a signed-in user with an e-mail', () async {
    await expectLater(
      FirebaseIdTokenSource(auth: FakeAuth()).changePassword('a', 'b'),
      failure(AuthFailureReason.notConfigured),
    );
    final user = FakeUser()..reauthError = authError('weak-password');
    await expectLater(
      FirebaseIdTokenSource(auth: FakeAuth(user)).changePassword('a', 'b'),
      failure(AuthFailureReason.weakPassword),
    );
  });

  test('linkedProviders reloads, and survives a failed reload', () async {
    final user = FakeUser(providers: ['password', 'google.com']);
    final source = FirebaseIdTokenSource(auth: FakeAuth(user));
    expect(await source.linkedProviders(), ['password', 'google.com']);
    user.reloadError = StateError('offline');
    expect(await source.linkedProviders(), ['password', 'google.com']);
    expect(await FirebaseIdTokenSource(auth: FakeAuth()).linkedProviders(), isEmpty);
  });

  test('signOut signs Firebase out, and Google only when it was started', () async {
    final google = FakeGoogle();
    final auth = FakeAuth(FakeUser());
    final source = FirebaseIdTokenSource(auth: auth, google: google);
    await source.signOut();
    expect(google.signedOut, 0);
    await source.prepareGoogle();
    await source.signOut();
    expect(auth.calls, ['signOut', 'signOut']);
    expect(google.signedOut, 1);
  });

  test('Google: prepare is remembered on success, not on failure', () async {
    final google = FakeGoogle()..prepareError = StateError('x');
    final source = FirebaseIdTokenSource(auth: FakeAuth(), google: google);
    await expectLater(source.prepareGoogle(), failure(AuthFailureReason.notConfigured));
    google.prepareError = null;
    await source.prepareGoogle();
    await source.prepareGoogle();
    expect(google.prepared, 2);
    await expectLater(
      FirebaseIdTokenSource(auth: FakeAuth()).prepareGoogle(),
      failure(AuthFailureReason.notConfigured),
    );
  });

  test('Google sign-in returns a Firebase id token; link uses the credential', () async {
    final auth = FakeAuth();
    final source = FirebaseIdTokenSource(auth: auth, google: FakeGoogle());
    expect(await source.signInWithGoogle(), 'id-1');
    expect(auth.credentialUsed, isNotNull);
    await source.linkGoogleCredential(GoogleAuthProvider.credential(idToken: 'g'));
    expect(auth.currentUser!.linked, isNotNull);
    await source.linkGoogle();
  });

  test('link without a user is refused; an already-linked provider maps', () async {
    final source = FirebaseIdTokenSource(auth: FakeAuth());
    await expectLater(
      source.linkGoogleCredential(GoogleAuthProvider.credential(idToken: 'g')),
      failure(AuthFailureReason.other),
    );
  });

  test('Apple: no fetcher means not configured; the sheet gets the hashed nonce', () async {
    await expectLater(FirebaseIdTokenSource(auth: FakeAuth()).signInWithApple(), failure(AuthFailureReason.notConfigured));
    String? seen;
    final auth = FakeAuth();
    final source = FirebaseIdTokenSource(
      auth: auth,
      appleFetcher: (hashed) async {
        seen = hashed;
        return const AppleCredentialData(identityToken: 'apple-jwt', givenName: 'A');
      },
    );
    expect(await source.signInWithApple(), 'id-1');
    expect(seen, matches(RegExp(r'^[0-9a-f]{64}$')));
    expect(auth.credentialUsed, isNotNull);
  });

  test('Apple: an empty identity token is refused', () async {
    await expectLater(
      FirebaseIdTokenSource.appleCredential(
        (_) async => const AppleCredentialData(identityToken: ''),
        AppleNonce.generate(),
      ),
      failure(AuthFailureReason.other),
    );
  });
}
