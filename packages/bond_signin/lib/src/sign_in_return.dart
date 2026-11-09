import 'sign_in_attempt.dart';

/// What the browser comes back with after the sign-in round trip.
enum SignInReturnKind {
  /// Web flow finished: `?signin=ok`. The session cookie is set.
  ok,

  /// Refused: `?signin=error&reason=<code>`.
  error,

  /// Native flow: `?attempt=<id>&code=<handoff>` or `?attempt=<id>&error=<code>`.
  native,

  /// An ordinary visit: nothing to do.
  none,
}

class SignInReturn {
  const SignInReturn(this.kind, {this.reason, this.attempt, this.code});

  /// Reads the returned address. Never throws; an unrelated address is [SignInReturnKind.none].
  factory SignInReturn.parse(Uri url) {
    final q = url.queryParameters;
    String? clean(String? v) => v == null || v.isEmpty ? null : v;
    switch (q['signin']) {
      case 'ok':
        return const SignInReturn(SignInReturnKind.ok);
      case 'error':
        return SignInReturn(SignInReturnKind.error, reason: clean(q['reason']) ?? 'unknown');
    }
    final attempt = clean(q['attempt']);
    final code = clean(q['code']);
    final error = clean(q['error']);
    if (attempt != null && (code != null || error != null)) {
      return SignInReturn(SignInReturnKind.native, attempt: attempt, code: code, reason: error);
    }
    return const SignInReturn(SignInReturnKind.none);
  }

  /// The query keys this class reads.
  static const _keys = ['signin', 'reason', 'attempt', 'code', 'error'];

  final SignInReturnKind kind;

  /// The refusal code (`reason` on web, `error` on native); null when none.
  final String? reason;

  /// The opaque attempt id the server echoed (native only).
  final String? attempt;

  /// The one-time hand-off code (native only; null on a native error).
  final String? code;

  /// True when this return carries a refusal.
  bool get isError => kind == SignInReturnKind.error || (kind == SignInReturnKind.native && reason != null);

  /// True when this is a native return for exactly the [pending] attempt. A
  /// return for any other attempt (a lured victim's browser) must be ignored.
  bool matches(SignInAttempt? pending) =>
      kind == SignInReturnKind.native && pending != null && attempt == pending.id;

  /// [url] without the return parameters, to put back in the address bar.
  static Uri cleaned(Uri url) {
    final rest = Map<String, String>.of(url.queryParameters)..removeWhere((k, _) => _keys.contains(k));
    // Uri.replace keeps the old query when given null, so rebuild without one.
    final bare = Uri(
      scheme: url.scheme,
      userInfo: url.userInfo,
      host: url.hasAuthority ? url.host : null,
      port: url.hasPort ? url.port : null,
      path: url.path,
      fragment: url.hasFragment ? url.fragment : null,
    );
    return rest.isEmpty ? bare : bare.replace(queryParameters: rest);
  }

  // No code in the text form: it is a credential until redeemed.
  @override
  String toString() => 'SignInReturn($kind, reason: $reason)';
}
