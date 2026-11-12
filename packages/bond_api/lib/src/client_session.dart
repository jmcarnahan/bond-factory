/// The session half of [ApiClient]: the shared renewal and the end-of-session hooks.
part of 'client.dart';

extension _ClientSession on ApiClient {
  Future<SessionRefresh> _renewOnce() {
    final running = _refreshing;
    if (running != null) return running;
    late final Future<SessionRefresh> f;
    f = _renewGuarded(onUnauthorized!).whenComplete(() {
      if (identical(_refreshing, f)) _refreshing = null;
    });
    _refreshing = f;
    return f;
  }

  // A hook that throws counts as a refusal.
  Future<SessionRefresh> _renewGuarded(Future<SessionRefresh> Function() hook) async {
    try { return await hook(); } catch (e) { _log('session renewal failed: ${e.runtimeType}'); }
    return SessionRefresh.rejected;
  }

  ErrorBody _readBody(int status, String text) {
    try {
      return ErrorBody.from(status, text);
    } catch (_) {
      return ErrorBody(status: status, message: 'HTTP $status');
    }
  }

  bool _endsSessionSafe(ErrorBody body) {
    try {
      return endsSession!(body);
    } catch (e) {
      _log('endsSession failed: ${e.runtimeType}');
      return true;
    }
  }

  Future<void> _run(Future<void> Function()? hook) async {
    try { await hook?.call(); } catch (e) { _log('session hook failed: ${e.runtimeType}'); }
  }

  Future<ApiException> _fail(
    int status,
    String text,
    String path, {
    required bool signedIn,
    required bool rejected,
  }) async {
    var error = ErrorBody.parse(status, text);
    if (error is Unauthorized && rejected) error = Unauthorized(error.message, error.code, true);
    if (ApiClient._isAuthPath(path) || !signedIn) return error;
    if (error is Unauthorized && !_endedFired) {
      _endedFired = true;
      if (error.code == 'session_revoked') await _run(onSessionRevoked);
      await _run(onSessionExpired);
    }
    if (error is Forbidden && error.code == 'deactivated' && !_deactivatedFired) {
      _deactivatedFired = true;
      await _run(onDeactivated);
    }
    return error;
  }
}
