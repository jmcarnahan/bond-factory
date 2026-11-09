/// Sign-in through an identity provider: the provider's id token is exchanged
/// for the server's session token.
library;

import 'package:bond_api/bond_api.dart';

import 'auth_failure.dart';
import 'gateway.dart';
import 'gateway_support.dart';
import 'id_token_source.dart';
import 'session.dart';

class FirebaseAuthGateway extends GatewayBase implements AuthGateway {
  FirebaseAuthGateway({required super.api,
    required super.tokens,
    required this.source,
    super.refreshTokens,
    super.onSessionEnded,
    super.onStorageFailure,
    super.authPrefix,
    super.rotationIds,
  });

  final IdTokenSource source;

  @override
  Future<AuthSession> signInDemo(String userId) async =>
      throw const AuthFailure(AuthFailureReason.notConfigured, code: 'demo_off');

  @override
  Future<AuthSession> signInWithIdToken(String idToken, {bool signIn = true}) => asAuthFailure(() async {
        final body = await api.postJson('$authPrefix/firebase', body: {'id_token': idToken, if (!signIn) 'sign_in': false});
        return accept(body, '$authPrefix/firebase');
      });

  @override
  Future<AuthSession> signInWithEmail(String email, String password) async {
    await source.signInWithEmail(email, password);
    final id = await source.currentIdToken(forceRefresh: true);
    if (id == null) throw const AuthFailure(AuthFailureReason.wrongCredentials, code: 'no_id_token');
    return signInWithIdToken(id);
  }

  @override
  Future<void> sendPasswordReset(String email) => source.sendPasswordReset(email);

  @override
  Future<void> changePassword(String current, String next) => source.changePassword(current, next);

  @override
  Future<List<String>> linkedProviders() => source.linkedProviders();

  /// A fresh id token (`forceRefresh`) exchanged at `POST /auth/refresh`.
  /// There is no refresh token in this contract.
  @override
  Future<AuthSession> exchangeForRefresh(String? expectedUserId) async {
    final id = await source.currentIdToken(forceRefresh: true);
    if (id == null) throw const AuthFailure(AuthFailureReason.wrongCredentials, code: 'no_identity_session');
    final body = await api.postJson('$authPrefix/refresh', body: {'id_token': id});
    return sessionFromAuthBody(body, path: '$authPrefix/refresh');
  }

  @override
  Future<void> signOut() async {
    await endServerSession();
    await source.signOut();
  }
}
