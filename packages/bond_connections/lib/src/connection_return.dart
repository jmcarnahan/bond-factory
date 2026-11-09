/// How a connect attempt ended.
enum ConnectionOutcome { connected, error }

/// What the browser comes back with after the provider's consent page:
/// `<redirect_to>?connection=connected|error&provider=<name>[&reason=<code>][&code=<handoff>]`.
/// A native-app flow adds `code`, the one-time hand-off for `ConnectionsApi.redeem`.
class ConnectionReturn {
  const ConnectionReturn(this.outcome, {this.provider, this.reason, this.code});

  /// Reads the returned address. Null when it carries no `connection`
  /// parameter or a value other than `connected` and `error`, so an ordinary
  /// visit to the page is never mistaken for a return.
  static ConnectionReturn? parse(Uri url) {
    final params = url.queryParameters;
    final outcome = switch (params['connection']) {
      'connected' => ConnectionOutcome.connected,
      'error' => ConnectionOutcome.error,
      _ => null,
    };
    if (outcome == null) return null;
    String? clean(String? v) => v == null || v.isEmpty ? null : v;
    return ConnectionReturn(outcome, provider: clean(params['provider']), reason: clean(params['reason']), code: clean(params['code']));
  }

  final ConnectionOutcome outcome;

  /// The provider the attempt was for; null when the address did not say.
  final String? provider;

  /// The short code the server gave for an error (`access_denied`, `unavailable`).
  final String? reason;

  /// The one-time hand-off code of a native flow; null for a web flow or an error.
  final String? code;

  bool get isError => outcome == ConnectionOutcome.error;

  /// [url] without the return parameters (`connection`, `provider`, `reason`, `code`), to put back in the address bar.
  static Uri cleaned(Uri url) {
    final rest = Map<String, String>.of(url.queryParameters)
      ..remove('connection')
      ..remove('provider')
      ..remove('reason')
      ..remove('code');
    // Uri.replace keeps the old query when given null, so rebuild without one.
    final bare = Uri(scheme: url.scheme, userInfo: url.userInfo, host: url.hasAuthority ? url.host : null,
        port: url.hasPort ? url.port : null, path: url.path, fragment: url.hasFragment ? url.fragment : null);
    return rest.isEmpty ? bare : bare.replace(queryParameters: rest);
  }

  @override
  String toString() => 'ConnectionReturn($outcome, $provider, $reason)';
}
