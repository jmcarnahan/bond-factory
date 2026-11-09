import 'package:bond_api/bond_api.dart';
import 'package:bond_json/bond_json.dart';

import 'status.dart';

/// The connections routes: list, start, disconnect.
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

  /// `GET /connections/{provider}/start`: the address to open in the browser.
  /// [redirectTo] must be on the server's allowlist.
  Future<Uri> startUrl(String provider, {String? redirectTo}) async {
    final path = _path(provider, '/start');
    final body = await client.getJson(path, query: {'redirect_to': ?redirectTo});
    final url = jstr(body, 'url');
    if (url == null || url.isEmpty) throw BadResponse(path, 'the answer has no url');
    return Uri.parse(url);
  }

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
