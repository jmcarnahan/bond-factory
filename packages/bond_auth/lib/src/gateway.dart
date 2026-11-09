/// The gateway contract between the app and the server's `/auth/*` routes.
library;

import 'package:bond_api/bond_api.dart';

import 'auth_failure.dart';
import 'providers.dart';
import 'session.dart';

abstract class AuthGateway {
  /// `POST /auth/demo`: only when the server has demo sign-in on.
  Future<AuthSession> signInDemo(String userId);

  /// `POST /auth/firebase`: exchanges a provider id token for a session.
  /// [signIn] false skips the server's last-sign-in bookkeeping.
  Future<AuthSession> signInWithIdToken(String idToken, {bool signIn = true});

  Future<AuthSession> signInWithEmail(String email, String password);
  Future<void> sendPasswordReset(String email);
  Future<void> changePassword(String current, String next);
  Future<List<String>> linkedProviders();

  /// Renews the session. Null when the server could not be reached (keep the
  /// session). Throws [AuthFailure] when the identity provider or the server
  /// refuses, and [SessionBelongsToAnotherPerson] when the renewal is for
  /// someone other than [expectedUserId] (nothing is stored then).
  Future<AuthSession?> refreshSession({String? expectedUserId});

  /// Ends the session on the server (failures ignored), clears the stored
  /// token and signs out of the identity provider.
  Future<void> signOut();

  /// `GET /auth/providers`.
  Future<AuthProviders> providers();
}

/// Adapts [AuthGateway.refreshSession] to `ApiClient.onUnauthorized`.
///
/// A session means `renewed`; null (offline) means `offline`; a refusal
/// ([AuthFailure]) or a session for another person means `rejected`. Any other
/// error is rethrown and the client counts it as a refusal.
Future<SessionRefresh> Function() renewalHook(AuthGateway g, {String? expectedUserId}) {
  return () async {
    try {
      final s = await g.refreshSession(expectedUserId: expectedUserId);
      return s == null ? SessionRefresh.offline : SessionRefresh.renewed;
    } on AuthFailure catch (e) {
      return e.reason == AuthFailureReason.network ? SessionRefresh.offline : SessionRefresh.rejected;
    } on SessionBelongsToAnotherPerson {
      return SessionRefresh.rejected;
    } on NetworkError {
      return SessionRefresh.offline;
    }
  };
}
