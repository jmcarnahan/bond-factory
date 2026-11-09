/// Demo sign-in: the server mints a session for a named seeded user. Only for
/// harnesses; the server answers 404 when demo auth is off.
library;

import 'package:bond_api/bond_api.dart';

import 'auth_failure.dart';
import 'gateway.dart';
import 'gateway_support.dart';
import 'session.dart';

class DemoAuthGateway extends GatewayBase implements AuthGateway {
  DemoAuthGateway({
    required super.api,
    required super.tokens,
    super.refreshTokens,
    super.onSessionEnded,
    super.onStorageFailure,
    super.rotationIds,
  });

  static const AuthFailure _unsupported = AuthFailure(AuthFailureReason.notConfigured, code: 'demo_only');

  Future<AuthSession> _post(String userId) async =>
      sessionFromAuthBody(await api.postJson('/auth/demo', body: {'user_id': userId}), path: '/auth/demo');

  @override
  Future<AuthSession> signInDemo(String userId) => asAuthFailure(() async {
        final session = await _post(userId);
        await tokens.save(session.token);
        return session;
      });

  @override
  Future<AuthSession> signInWithIdToken(String idToken, {bool signIn = true}) async => throw _unsupported;

  @override
  Future<AuthSession> signInWithEmail(String email, String password) async => throw _unsupported;

  @override
  Future<void> sendPasswordReset(String email) async => throw _unsupported;

  @override
  Future<void> changePassword(String current, String next) async => throw _unsupported;

  @override
  Future<List<String>> linkedProviders() async => const [];

  /// A demo session renews by signing in as the same user again. The user is
  /// [expectedUserId], else the one in the stored token.
  @override
  Future<AuthSession> exchangeForRefresh(String? expectedUserId) async {
    var userId = expectedUserId;
    final current = tokens.token;
    if (userId == null && current != null) {
      try {
        userId = AuthSession.fromToken(current).userId;
      } on FormatException {
        userId = null;
      }
    }
    if (userId == null) throw const AuthFailure(AuthFailureReason.wrongCredentials, code: 'no_session');
    return _post(userId);
  }

  @override
  Future<void> signOut() => endServerSession();
}
