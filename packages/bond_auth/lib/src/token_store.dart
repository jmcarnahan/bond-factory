/// Where the session token is kept. The api client reads it through
/// [TokenSource]; the gateway writes it.
library;

import 'package:bond_api/bond_api.dart';

/// A storage failure (the platform store refused or lost the value).
class TokenStoreException implements Exception {
  const TokenStoreException(this.message);

  final String message;

  @override
  String toString() => 'TokenStoreException: $message';
}

/// A [TokenSource] that can also persist. [token] is synchronous: it is the
/// value last loaded or saved.
abstract class TokenStore implements TokenSource {
  Future<String?> load();
  Future<void> save(String token);
  Future<void> clear();
}

class InMemoryTokenStore implements TokenStore {
  InMemoryTokenStore([this.token]);

  @override
  String? token;

  @override
  Future<String?> load() async => token;

  @override
  Future<void> save(String token) async => this.token = token;

  @override
  Future<void> clear() async => token = null;
}

/// Wraps a slower store (secure storage, a browser tab) and keeps the value in
/// memory so [token] can be read synchronously. Call [reload] after another
/// tab or isolate may have changed the stored value.
class ReloadableTokenStore implements TokenStore {
  ReloadableTokenStore(this._inner);

  final TokenStore _inner;
  String? _cached;

  @override
  String? get token => _cached;

  /// Re-reads the wrapped store and returns the value.
  Future<String?> reload() async => _cached = await _inner.load();

  @override
  Future<String?> load() => reload();

  @override
  Future<void> save(String token) async {
    await _inner.save(token);
    _cached = token;
  }

  @override
  Future<void> clear() async {
    // Inner first: if it fails the cache still matches what is stored.
    await _inner.clear();
    _cached = null;
  }
}

/// Clears a store when a sign-out signal arrives, so a session that ended on
/// the server does not linger. Wire [forget] to `ApiClient.onSessionExpired`,
/// `onSessionRevoked` and `onDeactivated`.
class LiveTokenForgetter {
  LiveTokenForgetter(this._store, {this.onForgotten});

  final TokenStore _store;

  /// Runs after the token was cleared (route to the sign-in screen here).
  final void Function()? onForgotten;

  Future<void> forget() async {
    await _store.clear();
    onForgotten?.call();
  }
}
