/// The identity provider seam: where a fresh id token comes from.
library;

import 'auth_failure.dart';

/// The Firebase-type-free half of an identity provider. The federated half
/// (Google, Apple) lives in `bond_auth_firebase`.
abstract interface class IdTokenSource {
  /// False when no provider is set up (the gateway then cannot sign in).
  bool get isConfigured;

  /// The current id token, or null when nobody is signed in with the provider.
  /// [forceRefresh] asks the provider for a newly minted one.
  Future<String?> currentIdToken({bool forceRefresh = false});

  Future<void> signInWithEmail(String email, String password);
  Future<void> sendPasswordReset(String email);
  Future<void> changePassword(String current, String next);

  /// Provider ids linked to the signed-in account (`password`, `google.com`).
  Future<List<String>> linkedProviders();
  Future<void> signOut();
}

/// The source for an app without an identity provider: every call but
/// `signOut` fails with [AuthFailureReason.notConfigured].
class NotConfiguredIdTokenSource implements IdTokenSource {
  const NotConfiguredIdTokenSource();

  static Never _fail() => throw const AuthFailure(AuthFailureReason.notConfigured);

  @override
  bool get isConfigured => false;

  @override
  Future<String?> currentIdToken({bool forceRefresh = false}) async => _fail();

  @override
  Future<void> signInWithEmail(String email, String password) async => _fail();

  @override
  Future<void> sendPasswordReset(String email) async => _fail();

  @override
  Future<void> changePassword(String current, String next) async => _fail();

  @override
  Future<List<String>> linkedProviders() async => _fail();

  /// Nothing is signed in with a provider, so there is nothing to end.
  @override
  Future<void> signOut() async {}
}

/// A scriptable source for tests and the demo. Signing in with an e-mail sets
/// the token to `mock:<email>`, the literal the example server accepts.
class FakeIdTokenSource implements IdTokenSource {
  FakeIdTokenSource({this.token, this.failWith, this.configured = true, List<String>? providers})
      : providers = providers ?? <String>['password'];

  /// The id token handed out; null means signed out.
  String? token;

  /// When set, every call throws it.
  Object? failWith;
  bool configured;
  List<String> providers;

  /// Method names in call order, e.g. `currentIdToken(force)`, `signOut`.
  final List<String> calls = [];

  void _record(String call) {
    calls.add(call);
    final f = failWith;
    if (f != null) throw f;
  }

  @override
  bool get isConfigured => configured;

  @override
  Future<String?> currentIdToken({bool forceRefresh = false}) async {
    _record(forceRefresh ? 'currentIdToken(force)' : 'currentIdToken');
    return token;
  }

  @override
  Future<void> signInWithEmail(String email, String password) async {
    _record('signInWithEmail');
    token = 'mock:${email.trim().toLowerCase()}';
  }

  @override
  Future<void> sendPasswordReset(String email) async => _record('sendPasswordReset');

  @override
  Future<void> changePassword(String current, String next) async => _record('changePassword');

  @override
  Future<List<String>> linkedProviders() async {
    _record('linkedProviders');
    return List.of(providers);
  }

  @override
  Future<void> signOut() async {
    _record('signOut');
    token = null;
  }
}
