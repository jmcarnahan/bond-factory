/// The seams between [ApiClient] and a session store.
library;

/// Where [ApiClient] reads the current session token. `bond_auth`'s token
/// store implements it; bond_api itself knows nothing about sessions.
abstract interface class TokenSource {
  /// The bearer token to send, or null when signed out.
  String? get token;
}

/// A fixed or settable [TokenSource], for tests and demos.
class StaticTokenSource implements TokenSource {
  StaticTokenSource([this.token]);

  @override
  String? token;
}

/// How a silent session renewal ended (the result of `onUnauthorized`).
enum SessionRefresh {
  /// A new session token is stored: the request can be sent again.
  renewed,

  /// The server or the identity provider refused: the person has to sign in again.
  rejected,

  /// Could not reach the server: keep the session, fail this request only.
  offline,
}

/// Paths that are how a session is made. A 401 or 403 from one of them never
/// triggers a renewal or a session hook. Matched against the end of the request
/// path, so an app prefix such as `/api/v1` does not matter.
const List<String> authPathsExcludedFromRenewal = ['/auth/firebase', '/auth/refresh', '/auth/demo'];
