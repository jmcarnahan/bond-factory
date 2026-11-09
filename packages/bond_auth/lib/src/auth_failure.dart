/// Why a sign-in or a session call failed, in terms a screen can word.
library;

import 'package:bond_api/bond_api.dart';

enum AuthFailureReason {
  wrongCredentials,
  invalidEmail,
  rateLimited,
  disabled,
  network,
  notConfigured,
  accountExistsWithDifferentCredential,
  cancelled,
  notInvited,
  appleRelay,
  alreadyLinked,
  weakPassword,
  other,
}

/// A sign-in refusal. [code] is the server's or the provider's named reason
/// when there is one.
class AuthFailure implements Exception {
  const AuthFailure(this.reason, {this.code, this.message, this.hint});

  /// Reads an API failure from `/auth/*` (or any authenticated call) as an
  /// [AuthFailure]. The server's `code` is kept for every status.
  ///
  /// - 403 `not_invited` (hint `apple_relay`: appleRelay), `deactivated`: disabled;
  ///   `identity_mismatch`, `email_not_verified` and the rest: other.
  /// - 401 without a code or `invalid_token`: wrongCredentials; `session_revoked`: other.
  /// - 429: rateLimited. 501 or `firebase_not_configured`, and a 404 (demo
  ///   sign-in is off): notConfigured.
  /// - No answer, or 503 (`auth_unavailable`, `db_unavailable`): network.
  factory AuthFailure.fromApi(ApiException e) {
    final code = _codeOf(e);
    final message = e.message;
    AuthFailure make(AuthFailureReason r, {String? hint}) =>
        AuthFailure(r, code: code, message: message, hint: hint);

    if (e is NetworkError) return make(AuthFailureReason.network);
    if (e is Forbidden) {
      return switch (code) {
        'not_invited' => make(
            e.hint == 'apple_relay' ? AuthFailureReason.appleRelay : AuthFailureReason.notInvited,
            hint: e.hint,
          ),
        'deactivated' => make(AuthFailureReason.disabled),
        _ => make(AuthFailureReason.other, hint: e.hint),
      };
    }
    if (e is Unauthorized) {
      return make(code == null || code == 'invalid_token' ? AuthFailureReason.wrongCredentials : AuthFailureReason.other);
    }
    final status = e.statusCode;
    if (status == 429) return AuthFailure(AuthFailureReason.rateLimited, code: code ?? 'rate_limited', message: message);
    if (status == 501 || code == 'firebase_not_configured' || e is NotFound) {
      return make(AuthFailureReason.notConfigured);
    }
    if (status == 503) return make(AuthFailureReason.network);
    return make(AuthFailureReason.other);
  }

  static String? _codeOf(ApiException e) => switch (e) {
        Unauthorized() => e.code,
        Forbidden() => e.code,
        NotFound() => e.code,
        Conflict() => e.code,
        BadRequest() => e.code,
        ValidationError() => e.code,
        ServerError() => e.code,
        _ => null,
      };

  final AuthFailureReason reason;
  final String? code;
  final String? message;

  /// A second named detail from the server (`apple_relay` on `not_invited`).
  final String? hint;

  @override
  String toString() => 'AuthFailure(${reason.name}${code == null ? '' : ', $code'})';
}
