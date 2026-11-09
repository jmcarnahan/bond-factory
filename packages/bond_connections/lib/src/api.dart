import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'status.dart';
import 'wanted.dart';

/// The connections routes: list, start, redeem (native apps), disconnect.
///
/// Starting a connection is a hand-off to the browser: [startUrl] returns the
/// address the app navigates to at top level (it carries the session cookie
/// and sets the sign-in nonce cookie before the provider's consent page). The
/// provider then sends the browser back to the `redirectTo` address; read that
/// with `ConnectionReturn.parse` and call [list] again. Nothing needs to be
/// kept across the redirect.
class ConnectionsApi {
  ConnectionsApi(this.client, {this.prefix = '/connections'});

  final ApiClient client;
  final String prefix;

  String _path(String provider, [String tail = '']) => '$prefix/${Uri.encodeComponent(provider)}$tail';

  /// `GET /connections`: one status per configured provider.
  Future<List<ConnectionStatus>> list() async {
    final body = await client.request('GET', prefix);
    if (body is! List) throw BadResponse(prefix, 'expected a list, got ${describeJsonType(body)}');
    try {
      return jlistOf(body, ConnectionStatus.fromJson);
    } on JsonShapeError catch (e) {
      throw BadResponse(prefix, e.toString());
    }
  }

  /// `GET /connections` read as the whole answer: the statuses and the scope
  /// sets the signed-in person's role wants. Accepts the bare array of an older
  /// server (no wanted sets) and `{connections, wanted}`.
  Future<ConnectionList> listAll() async {
    final body = await client.request('GET', prefix);
    try {
      return ConnectionList.fromJson(body);
    } on JsonShapeError catch (e) {
      throw BadResponse(prefix, e.toString());
    }
  }

  /// The wanted scope sets from `GET /connections`; those with `granted` false
  /// are the asks to show. Empty on a server that reports none.
  Future<List<WantedSet>> wanted() async => (await listAll()).wanted;

  /// `GET /connections/{provider}/start`: the address to open in the browser.
  /// [redirectTo] must be on the server's allowlist. With [native] (a phone
  /// app opening the system browser) the server takes [redirectTo] from its
  /// native allowlist (an app-scheme address), needs no cookie in that
  /// browser, and returns to the app with a one-time `code`; read it with
  /// `ConnectionReturn.parse` and pass it to [redeem]. [set] is a wanted set id
  /// (`WantedSet.id`): the server asks only that set's scopes, for the
  /// signed-in account.
  ///
  /// A native start needs the device binding: [deviceChallenge] (the hex
  /// SHA-256 of a 32-byte device secret the app keeps) and [attempt] (the
  /// opaque id the server echoes on return). Both are required when [native]
  /// is true (`ArgumentError` otherwise). The app generates them (for example
  /// with `bond_signin`'s `SignInAttempt`) and keeps the secret for [redeem].
  Future<Uri> startUrl(
    String provider, {
    String? redirectTo,
    bool native = false,
    String? set,
    String? deviceChallenge,
    String? attempt,
  }) async {
    if (native && (deviceChallenge == null || deviceChallenge.isEmpty || attempt == null || attempt.isEmpty)) {
      throw ArgumentError('a native start needs deviceChallenge and attempt');
    }
    final path = _path(provider, '/start');
    final body = await client.getJson(
      path,
      query: {
        'redirect_to': ?redirectTo,
        if (native) 'mode': 'native',
        'set': ?set,
        if (native) 'device_challenge': deviceChallenge,
        if (native) 'attempt': attempt,
      },
    );
    final url = jstr(body, 'url');
    if (url == null || url.isEmpty) throw BadResponse(path, 'the answer has no url');
    return Uri.parse(url);
  }

  /// `POST /connections/{provider}/redeem`: trades the one-time [code] from a
  /// native return for the connection's status. The client's bearer token must
  /// belong to the user who started the flow; a code works once. [deviceSecret]
  /// is the secret whose SHA-256 was sent as `deviceChallenge` at start; a code
  /// presented with any other secret is burned. [deviceLabel] is an optional
  /// short name for the device.
  Future<ConnectionStatus> redeem(
    String provider,
    String code, {
    required String deviceSecret,
    String? deviceLabel,
  }) async =>
      ConnectionStatus.fromJson(
        await client.postJson(
          _path(provider, '/redeem'),
          body: {'code': code, 'device_secret': deviceSecret, 'device_label': ?deviceLabel},
        ),
      );

  /// `DELETE /connections/{provider}`: the status after the disconnect.
  Future<ConnectionStatus> disconnect(String provider) async =>
      ConnectionStatus.fromJson(await client.deleteJson(_path(provider)));
}

/// Routes only the example server has, and only in fake mode.
class DemoConnectionsApi {
  DemoConnectionsApi(this.client, {this.prefix = '/connections'});

  final ApiClient client;
  final String prefix;

  /// `POST /connections/{provider}/simulate-expiry`: the provider now refuses
  /// the stored grant. Returns the status afterwards.
  Future<ConnectionStatus> simulateExpiry(String provider) async => ConnectionStatus.fromJson(
        await client.postJson('$prefix/${Uri.encodeComponent(provider)}/simulate-expiry'),
      );
}
