/// Pieces both gateways share: the answer reader, logout, providers and the
/// single-flight session renewal.
library;

import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'auth_failure.dart';
import 'providers.dart';
import 'refresh_token_store.dart';
import 'rotation_ids.dart';
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
    refreshToken: _refreshTokenOf(body),
  );
}

String? _refreshTokenOf(Map<String, Object?> body) {
  final r = jstr(body, 'refresh_token');
  return r == null || r.isEmpty ? null : r;
}

/// The 401 codes that end a session for good: the refresh token or the session
/// behind it is dead, so keeping either token would only repeat the failure.
const Set<String> sessionEndCodes = {
  'refresh_reused',
  'refresh_expired',
  'refresh_revoked',
  'session_revoked',
  'invalid_handoff',
};

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
  GatewayBase({
    required this.api,
    required this.tokens,
    this.refreshTokens = const NoRefreshTokenStore(),
    this.onSessionEnded,
    this.onStorageFailure,
    this.authPrefix = '/auth',
    RotationIds? rotationIds,
  }) : rotationIds = rotationIds ?? RotationIds();

  final ApiClient api;
  final TokenStore tokens;

  /// Where the rotating refresh token lives. [NoRefreshTokenStore] (the
  /// default) means the web cookie carries it; delivery follows this store.
  final RefreshTokenStore refreshTokens;

  /// Where the server mounts the auth routes (`/api/v1/auth` for the apps).
  /// Every path this package calls is built from it.
  final String authPrefix;

  /// The id sent with a rotation. Reused when the same rotation is retried
  /// after no answer, replaced after a stored success.
  final RotationIds rotationIds;

  /// Called after a renewal ended the session for good, with the server's code
  /// (see [sessionEndCodes]). Both stores are already cleared. Settable so a
  /// screen can attach after the gateway was built.
  void Function(String code)? onSessionEnded;

  /// Called when a store write failed (secure storage refused). The session
  /// stays in memory; the app may warn that it will not survive a restart.
  void Function(Object error)? onStorageFailure;

  bool _rotationLoaded = false;

  /// The code of the last session end, or null when none ended since the last
  /// sign-in. The UI reads it to word the message (`refresh_reused`).
  String? lastEndReason;

  int _generation = 0;
  final Map<String?, Future<AuthSession?>> _flights = {};

  /// Saves the answer's refresh token (when it has one), then its token, and
  /// returns the session. The refresh token goes first: if the app dies
  /// between the two writes the newest refresh token is on disk, and the
  /// server's grace window covers the old access token.
  Future<AuthSession> accept(Map<String, Object?> body, String path) async {
    final session = sessionFromAuthBody(body, path: path);
    final stored = await _store(session);
    lastEndReason = null;
    rotationIds.succeeded();
    if (stored) await _guard(() => refreshTokens.saveRotation(null));
    return session;
  }

  /// Writes the refresh token, then the access token. A failing write keeps the
  /// in-memory session, is reported through [onStorageFailure] and returns false.
  Future<bool> _store(AuthSession session) async {
    var ok = true;
    final refresh = session.refreshToken;
    if (refresh != null) ok = await _guard(() => refreshTokens.save(refresh));
    if (!await _guard(() => tokens.save(session.token))) ok = false;
    return ok;
  }

  Future<bool> _guard(Future<void> Function() write) async {
    try {
      await write();
      return true;
    } on Object catch (e) {
      onStorageFailure?.call(e);
      return false;
    }
  }

  /// One renewal attempt: ask the server for a session WITHOUT storing it.
  /// May throw [ApiException] or [AuthFailure]; the caller maps them. A
  /// gateway that rotates a refresh token sends `rotationIds.current`.
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
      // Another isolate may have rotated the token since this one last read it.
      await refreshTokens.reload();
      if (!_rotationLoaded) {
        // Cold start: a rotation an earlier run sent but never stored is retried with its id.
        _rotationLoaded = true;
        final saved = await refreshTokens.loadRotation();
        if (saved != null) rotationIds.adopt(saved);
      }
      await _guard(() => refreshTokens.saveRotation(rotationIds.current));
      session = await exchangeForRefresh(expectedUserId);
    } on ApiException catch (e) {
      if (isOfflineFailure(e)) return null;
      final failure = AuthFailure.fromApi(e);
      await _endIfFinal(failure.code, generation);
      throw failure;
    } on AuthFailure catch (e) {
      // A busy or unreachable identity provider has not refused the person.
      if (e.reason == AuthFailureReason.network || e.reason == AuthFailureReason.rateLimited) return null;
      await _endIfFinal(e.code, generation);
      rethrow;
    }
    if (expectedUserId != null && session.userId != expectedUserId) {
      throw SessionBelongsToAnotherPerson(session.userId);
    }
    if (generation != _generation) return null; // signed out meanwhile
    final stored = await _store(session);
    if (stored) {
      // Only a stored success retires the id: if the write failed, a retry
      // must carry the same id so the server treats it as a lost answer.
      rotationIds.succeeded();
      await _guard(() => refreshTokens.saveRotation(null));
    }
    return session;
  }

  /// A final code from the server ends the session: clear both stores, record
  /// why, tell the UI. Skipped when the person already signed out meanwhile.
  Future<void> _endIfFinal(String? code, int generation) async {
    if (code == null || !sessionEndCodes.contains(code) || generation != _generation) return;
    _generation++;
    await _clearStores();
    lastEndReason = code;
    onSessionEnded?.call(code);
  }

  Future<void> _clearStores() async {
    await refreshTokens.clear();
    await tokens.clear();
    await _guard(() => refreshTokens.saveRotation(null));
    rotationIds.succeeded();
  }

  Future<AuthProviders> providers() async =>
      AuthProviders.fromJson(await asAuthFailure(() => api.getJson('$authPrefix/providers')));

  /// `POST /auth/logout` (failures ignored; the refresh token goes in the body
  /// when this device holds one), then forget both tokens. A renewal still in
  /// flight will not store its result.
  Future<void> endServerSession() async {
    _generation++;
    String? refresh;
    try {
      refresh = await refreshTokens.load();
    } on Object {
      refresh = null;
    }
    try {
      await api.postJson('$authPrefix/logout', body: refresh == null ? null : {'refresh_token': refresh});
    } on ApiException {
      // The session is ending anyway; the cookie or token dies with the client.
    }
    await _clearStores();
    lastEndReason = null;
  }
}
