/// The signed-in session as the client sees it.
library;

import 'dart:convert';

/// A session token and what its payload says. The payload is decoded, not
/// verified: the server is the authority, the client only displays it.
class AuthSession {
  const AuthSession({
    required this.token,
    required this.userId,
    this.claims = const {},
    this.capabilities = const [],
    this.user = const {},
    this.refreshToken,
  });

  /// Decodes the JWT payload. Throws [FormatException] when [token] is not a
  /// JWT or carries no `sub`.
  factory AuthSession.fromToken(String token) {
    final parts = token.split('.');
    if (parts.length != 3) throw const FormatException('not a JWT');
    final Object? payload;
    try {
      payload = jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))));
    } on FormatException {
      throw const FormatException('unreadable JWT payload');
    }
    if (payload is! Map) throw const FormatException('JWT payload is not an object');
    final claims = {for (final e in payload.entries) e.key.toString(): e.value};
    final sub = claims['sub'];
    if (sub is! String || sub.isEmpty) throw const FormatException('JWT has no sub');
    final caps = claims['capabilities'];
    return AuthSession(
      token: token,
      userId: sub,
      claims: claims,
      capabilities: caps is List ? [for (final c in caps) c.toString()] : const [],
    );
  }

  final String token;
  final String userId;
  final Map<String, Object?> claims;
  final List<String> capabilities;

  /// The `user` object the server returned beside the token (`id`, `email`,
  /// `name`, ...). Empty when the session was made from a bare token.
  final Map<String, Object?> user;

  /// The rotating refresh token that came with the session on a body-delivery
  /// (native) sign-in. Null on web, where an HttpOnly cookie carries it, and for
  /// sessions made from a bare token.
  final String? refreshToken;

  /// True when `exp` is in the past on this device's clock. A token without
  /// `exp` never reads as expired here.
  bool isExpiredAt(DateTime now) {
    final exp = claims['exp'];
    if (exp is! num) return false;
    return exp.toInt() * 1000 <= now.millisecondsSinceEpoch;
  }

  bool get isExpired => isExpiredAt(DateTime.now());
}

/// A renewal produced a session for another person than the one who was signed
/// in. The new token is NOT stored.
class SessionBelongsToAnotherPerson implements Exception {
  const SessionBelongsToAnotherPerson(this.userId);

  /// The user the server returned.
  final String userId;

  @override
  String toString() => 'SessionBelongsToAnotherPerson($userId)';
}
