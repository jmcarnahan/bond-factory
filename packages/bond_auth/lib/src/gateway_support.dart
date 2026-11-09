/// Pieces both gateways share: the answer reader, logout, providers and the
/// single-flight session renewal.
library;

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'auth_failure.dart';
import 'providers.dart';
import 'session.dart';
import 'token_store.dart';

/// Reads `{token, user}` into a session. The token is decoded for its claims
/// when it is a JWT; the `user` object wins for id and capabilities.
AuthSession sessionFromAuthBody(Map<String, Object?> body, {String path = '/auth'}) {
  final token = jstr(body, 'token');
  if (token == null || token.isEmpty) throw BadResponse(path, 'no token in the answer');
  final user = jmap(body, 'user') ?? const <String, Object?>{};
  AuthSession? decoded;
  try {
    decoded = AuthSession.fromToken(token);
  } on FormatException {
    decoded = null;
  }
  final userId = jstr(user, 'id') ?? decoded?.userId;
  if (userId == null) throw BadResponse(path, 'no user id in the answer');
  final caps = user['capabilities'];
  return AuthSession(
    token: token,
    userId: userId,
    claims: decoded?.claims ?? const {},
    capabilities: caps is List ? [for (final c in caps) c.toString()] : decoded?.capabilities ?? const [],
    user: user,
  );
}

/// Runs [call], turning an [ApiException] into an [AuthFailure].
Future<T> asAuthFailure<T>(Future<T> Function() call) async {
  try {
    return await call();
  } on ApiException catch (e) {
    throw AuthFailure.fromApi(e);
  }
}

/// True when the server has not answered about the session: no answer, a
/// server that is down (5xx except 501) or busy (408, 429).
bool isOfflineFailure(ApiException e) {
  if (e is NetworkError) return true;
  final status = e.statusCode ?? 0;
  return (status >= 500 && status != 501) || status == 408 || status == 429;
}

/// What both gateways do the same way.
abstract class GatewayBase {
  GatewayBase({required this.api, required this.tokens});

  final ApiClient api;
  final TokenStore tokens;

  int _generation = 0;
  final Map<String?, Future<AuthSession?>> _flights = {};

  /// Saves the answer's token and returns the session.
  Future<AuthSession> accept(Map<String, Object?> body, String path) async {
    final session = sessionFromAuthBody(body, path: path);
    await tokens.save(session.token);
    return session;
  }

  /// One renewal attempt: ask the server for a session WITHOUT storing it.
  /// May throw [ApiException] or [AuthFailure]; the caller maps them.
  Future<AuthSession> exchangeForRefresh(String? expectedUserId);

  /// Single flight per [expectedUserId]: callers that arrive while a renewal
  /// runs share its result. Null when the server could not be reached or
  /// when the person signed out while it ran (nothing is stored then).
  Future<AuthSession?> refreshSession({String? expectedUserId}) {
    final running = _flights[expectedUserId];
    if (running != null) return running;
    late final Future<AuthSession?> f;
    f = _renew(expectedUserId).whenComplete(() {
      if (identical(_flights[expectedUserId], f)) _flights.remove(expectedUserId);
    });
    _flights[expectedUserId] = f;
    return f;
  }

  Future<AuthSession?> _renew(String? expectedUserId) async {
    final generation = _generation;
    final AuthSession session;
    try {
      session = await exchangeForRefresh(expectedUserId);
    } on ApiException catch (e) {
      if (isOfflineFailure(e)) return null;
      throw AuthFailure.fromApi(e);
    } on AuthFailure catch (e) {
      // A busy or unreachable identity provider has not refused the person.
      if (e.reason == AuthFailureReason.network || e.reason == AuthFailureReason.rateLimited) return null;
      rethrow;
    }
    if (expectedUserId != null && session.userId != expectedUserId) {
      throw SessionBelongsToAnotherPerson(session.userId);
    }
    if (generation != _generation) return null; // signed out meanwhile
    await tokens.save(session.token);
    return session;
  }

  Future<AuthProviders> providers() async =>
      AuthProviders.fromJson(await asAuthFailure(() => api.getJson('/auth/providers')));

  /// `POST /auth/logout` (failures ignored), then forget the token. A renewal
  /// still in flight will not store its result.
  Future<void> endServerSession() async {
    _generation++;
    try {
      await api.postJson('/auth/logout');
    } on ApiException {
      // The session is ending anyway; the cookie or token dies with the client.
    }
    await tokens.clear();
  }
}
