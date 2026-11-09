/// Where the rotating refresh token is kept on a device. On web the HttpOnly
/// cookie carries it and [NoRefreshTokenStore] is used.
library;

/// Storage for the refresh token of a body-delivery (native) session.
abstract interface class RefreshTokenStore {
  Future<String?> load();
  Future<void> save(String token);
  Future<void> clear();

  /// Re-reads the persisted value so two isolates share one token. Called
  /// before every rotation. Implementations without a cache have nothing to do
  /// and complete at once.
  Future<void> reload();
}

/// Keeps the token in memory only.
class InMemoryRefreshTokenStore implements RefreshTokenStore {
  InMemoryRefreshTokenStore([this._token]);

  String? _token;

  @override
  Future<String?> load() async => _token;

  @override
  Future<void> save(String token) async => _token = token;

  @override
  Future<void> clear() async => _token = null;

  @override
  Future<void> reload() async {}
}

/// Stores nothing: the web session cookie carries the refresh token, so the
/// gateway sends no body token (delivery follows the store, never the platform).
class NoRefreshTokenStore implements RefreshTokenStore {
  const NoRefreshTokenStore();

  @override
  Future<String?> load() async => null;

  @override
  Future<void> save(String token) async {}

  @override
  Future<void> clear() async {}

  @override
  Future<void> reload() async {}
}
