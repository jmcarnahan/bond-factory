import 'package:bond_api/bond_api.dart';
import 'package:bond_auth/bond_auth.dart' show AuthProviders;
import 'package:bond_json/bond_json.dart';

import 'sign_in_attempt.dart';

/// The `<prefix>/signin/*` routes (prefix `/auth` by default). Holds no state: the caller keeps the pending
/// [SignInAttempt] (and may persist it) between [startNative] and [redeem].
class SignInApi {
  SignInApi(this.client, {this.prefix = '/auth'});

  final ApiClient client;
  final String prefix;

  String _path(String provider, String tail) => '$prefix/signin/${Uri.encodeComponent(provider)}$tail';

  /// `POST /auth/signin/{provider}/start` for a browser. The server sets the
  /// nonce cookie on this answer (the call must carry credentials), then the
  /// page navigates to the returned address at top level. [redirectTo] must be
  /// on the server's allowlist.
  Future<Uri> startWeb(String provider, {required String redirectTo}) async {
    final path = _path(provider, '/start');
    final body = await client.postJson(path, body: {'redirect_to': redirectTo, 'mode': 'web'});
    return _url(body, path);
  }

  /// `POST /auth/signin/{provider}/start` for a phone app. Returns the fresh
  /// attempt and the address to open in the system browser. [returnUrl] is the
  /// full return address (what `NativeReturn.choose` returns, for instance
  /// `https://<api>/app/return/<provider>`); it is sent as `redirect_to`
  /// unchanged. The return comes back with `attempt` and `code` (or `error`).
  Future<(SignInAttempt, Uri)> startNative(String provider, {required Uri returnUrl}) async {
    final attempt = SignInAttempt.generate();
    final path = _path(provider, '/start');
    final body = await client.postJson(path, body: {
      'mode': 'native',
      'device_challenge': attempt.deviceChallenge,
      'attempt': attempt.id,
      'redirect_to': returnUrl.toString(),
    });
    return (attempt, _url(body, path));
  }

  /// `POST /auth/signin/redeem`: trades the hand-off [code] and the device
  /// secret of [attempt] for `{token, refresh_token, user}`. A code works once;
  /// a wrong secret burns it. [deviceLabel] names the device on the server's
  /// session list.
  Future<Map<String, Object?>> redeem(SignInAttempt attempt, String code, {String? deviceLabel}) =>
      client.postJson('$prefix/signin/redeem', body: {
        'code': code,
        'device_secret': attempt.deviceSecret,
        'device_label': ?deviceLabel,
      });

  /// `GET /auth/providers`: the sign-in methods on offer.
  Future<AuthProviders> providers() async => AuthProviders.fromJson(await client.getJson('$prefix/providers'));

  Uri _url(Map<String, Object?> body, String path) {
    final url = jstr(body, 'url');
    if (url == null || url.isEmpty) throw BadResponse(path, 'the answer has no url');
    return Uri.parse(url);
  }
}

/// The name the contract uses for [SignInApi].
typedef SignInClient = SignInApi;
