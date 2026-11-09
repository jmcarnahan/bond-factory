import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart';

import 'sign_in_api.dart';
import 'sign_in_attempt.dart';

/// The session gateway for direct sign-in: the server owns the identity
/// provider round trip, this class only completes and renews the session.
///
/// Delivery follows the injected `refreshTokens` store, never the platform:
/// [NoRefreshTokenStore] (web) means the HttpOnly cookie carries the refresh
/// token and the server relies on that cookie (whether requests carry
/// credentials is the app's http client's business); any other store means body
/// delivery (the refresh token is saved before the access token).
///
/// E-mail and password methods are not supported here and throw
/// [UnsupportedError]; the break-glass sign-in uses `FirebaseAuthGateway`.
class OidcAuthGateway extends GatewayBase implements AuthGateway {
  OidcAuthGateway({
    required super.api,
    required super.tokens,
    super.refreshTokens,
    super.onSessionEnded,
    super.onStorageFailure,
    super.authPrefix,
    super.rotationIds,
  }) : _signIn = SignInApi(api, prefix: authPrefix);

  final SignInApi _signIn;

  /// Web: the browser came back with `signin=ok` and the cookie is set. Asks
  /// the server for the access token (`POST /auth/refresh` with `{}`) and
  /// stores it. Throws [AuthFailure] when the server refuses.
  Future<AuthSession> completeWeb() => asAuthFailure(() async {
        final body = await api.postJson('$authPrefix/refresh', body: <String, Object?>{});
        return accept(body, '$authPrefix/refresh');
      });

  /// Native: the return carried [code] for [attempt]. Redeems it with the
  /// device secret and stores the refresh token, then the access token.
  /// [deviceLabel] names the device on the server's session list.
  Future<AuthSession> completeNative(SignInAttempt attempt, String code, {String? deviceLabel}) =>
      asAuthFailure(() async {
        final body = await _signIn.redeem(attempt, code, deviceLabel: deviceLabel);
        return accept(body, '$authPrefix/signin/redeem');
      });

  @override
  Future<AuthSession> exchangeForRefresh(String? expectedUserId) async {
    final refresh = await refreshTokens.load();
    final body = refresh == null || refresh.isEmpty
        // Cookie delivery: the browser sends the refresh cookie itself.
        ? <String, Object?>{'rotation_id': rotationIds.current}
        : <String, Object?>{
            'refresh_token': refresh,
            'rotation_id': rotationIds.current,
            'delivery': 'body',
          };
    return sessionFromAuthBody(await api.postJson('$authPrefix/refresh', body: body), path: '$authPrefix/refresh');
  }

  @override
  Future<AuthProviders> providers() => asAuthFailure(_signIn.providers);

  @override
  Future<void> signOut() => endServerSession();

  @override
  Future<List<String>> linkedProviders() async => const [];

  static UnsupportedError _no(String what) =>
      UnsupportedError('$what is not part of direct sign-in; use the break-glass gateway');

  @override
  Future<AuthSession> signInDemo(String userId) async => throw _no('Demo sign-in');

  @override
  Future<AuthSession> signInWithIdToken(String idToken, {bool signIn = true}) async => throw _no('Sign-in with an id token');

  @override
  Future<AuthSession> signInWithEmail(String email, String password) async => throw _no('E-mail and password sign-in');

  @override
  Future<void> sendPasswordReset(String email) async => throw _no('Password reset');

  @override
  Future<void> changePassword(String current, String next) async => throw _no('Password change');
}
